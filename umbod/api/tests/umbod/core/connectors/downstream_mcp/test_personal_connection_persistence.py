import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from tests.persistence_runtime import prepared_inmemory_runtime
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.personal_connections import (
    Authorized,
    CanonicalPrincipal,
    PersonalConnection,
    PersonalConnectionKey,
    PersonalConnectionStore,
    ReplacePersonalAuthorization,
    SetPersonalConnectionEnabled,
    StalePersonalConnectionRevision,
)
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.stores import SaveConnectorDefinition, create_downstream_mcp_stores
from umbod.core.connectors.downstream_mcp.stores.personal_connections import (
    EncryptedPersonalConnectionStore,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    PERSONAL_CONNECTION_TABLE,
    PersonalConnectionRecordKey,
)
from umbod.core.persistence import (
    AllFields,
    NoFilter,
    PersistenceRuntime,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


@pytest_asyncio.fixture
async def runtime() -> AsyncIterator[PersistenceRuntime]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_encrypted_personal_state_survives_store_recreation(
    runtime: PersistenceRuntime,
) -> None:
    bundle = await create_downstream_mcp_stores("encryption-secret", runtime.database)
    await bundle.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
        connector_id="alpha", display_name="Alpha", endpoint_url="https://alpha.example/mcp",
        authorization_mode="personal",
    )))
    store: PersonalConnectionStore = bundle.personal_connections
    key = PersonalConnectionKey(
        principal=CanonicalPrincipal(namespace="trusted", subject="owner"),
        connector_id="alpha",
    )
    state = await store.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    assert isinstance(state, PersonalConnection)
    saved = await store.replace_authorization(
        ReplacePersonalAuthorization(
            key=key,
            expected_revision=state.revision,
            authorization=Authorized(authorization="never-plaintext-authorization"),
        )
    )
    restored: PersonalConnectionStore = EncryptedPersonalConnectionStore(
        runtime.database,
        AuthenticatedTextCipher("encryption-secret"),
    )
    assert await restored.get(key) == saved
    async with runtime.database.session(mode=TransactionMode.READ_WRITE) as session:
        row = await session.find_one(
            PERSONAL_CONNECTION_TABLE,
            Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
        )
    assert row is not None
    assert "never-plaintext-authorization" not in row.document


@pytest.mark.asyncio
async def test_independent_stores_serialize_competing_authorization_writes(
    runtime: PersistenceRuntime,
) -> None:
    first: PersonalConnectionStore = EncryptedPersonalConnectionStore(
        runtime.database,
        AuthenticatedTextCipher("secret"),
    )
    second: PersonalConnectionStore = EncryptedPersonalConnectionStore(
        runtime.database,
        AuthenticatedTextCipher("secret"),
    )
    key = PersonalConnectionKey(
        principal=CanonicalPrincipal(namespace="trusted", subject="owner"),
        connector_id="alpha",
    )
    current = await first.set_enabled(
        SetPersonalConnectionEnabled(key=key, enabled=True)
    )
    assert isinstance(current, PersonalConnection)
    results = await asyncio.gather(
        first.replace_authorization(
            ReplacePersonalAuthorization(
                key=key,
                expected_revision=current.revision,
                authorization=Authorized(authorization="one"),
            )
        ),
        second.replace_authorization(
            ReplacePersonalAuthorization(
                key=key,
                expected_revision=current.revision,
                authorization=Authorized(authorization="two"),
            )
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, PersonalConnection) for result in results) == 1
    assert (
        sum(isinstance(result, StalePersonalConnectionRevision) for result in results)
        == 1
    )
    assert await first.get(key) == await second.get(key)


@pytest.mark.parametrize("tampered_field", ("namespace", "subject", "connector_id"))
@pytest.mark.asyncio
async def test_decrypted_ownership_must_match_requested_row(
    runtime: PersistenceRuntime, tampered_field: str
) -> None:
    store: PersonalConnectionStore = EncryptedPersonalConnectionStore(
        runtime.database, AuthenticatedTextCipher("secret")
    )
    principal = CanonicalPrincipal(namespace="trusted", subject="owner")
    key = PersonalConnectionKey(principal=principal, connector_id="alpha")
    await store.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    async with runtime.database.session(
        mode=TransactionMode.SERIALIZED_WRITE
    ) as session:
        row = await session.find_one(
            PERSONAL_CONNECTION_TABLE,
            Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
        )
        assert row is not None
        copied = row.model_copy(update={tampered_field: "victim"})
        record_key = PersonalConnectionRecordKey(
            namespace=copied.namespace,
            subject=copied.subject,
            connector_id=copied.connector_id,
        )
        await session.upsert(
            PERSONAL_CONNECTION_TABLE, UpsertCommand(key=record_key, row=copied)
        )
    target = PersonalConnectionKey(
        principal=CanonicalPrincipal(
            namespace=copied.namespace, subject=copied.subject
        ),
        connector_id=copied.connector_id,
    )
    with pytest.raises(ValueError, match="ownership mismatch"):
        await store.get(target)
