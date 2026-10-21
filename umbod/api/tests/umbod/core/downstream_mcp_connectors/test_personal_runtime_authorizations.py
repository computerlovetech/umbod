import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import SecretStr, ValidationError

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import (
    AbsentPersonalRefreshToken,
    ExpiringPersonalToken,
    PersonalOAuthGrant,
    UnknownPersonalTokenLifetime,
    authorize_personal_grant,
)
from umbod.core.connectors.downstream_mcp.personal_connections.models import (
    Authorized,
    CanonicalPrincipal,
    PersonalConnectionKey,
    ReplacePersonalAuthorization,
    SetPersonalConnectionEnabled,
)
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import (
    PersonalRuntimeAuthorizationQuery,
    PersonalRuntimeUnavailable,
)
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import (
    PersonalRuntimeAuthorizationStore,
)
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import (
    PersonalOAuthConfigurationQuery,
    PersonalOAuthSettings,
    PreconfiguredPublicOAuthClient,
    ReplacePersonalOAuthConfiguration,
)
from umbod.core.connectors.downstream_mcp.stores import (
    DownstreamMcpStores,
    SaveConnectorDefinition,
    create_downstream_mcp_stores,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configuration_schema import (
    PERSONAL_OAUTH_CONFIGURATION_TABLE,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configurations import (
    install_personal_oauth_configuration,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_DEFINITION_TABLE,
    PERSONAL_CONNECTION_TABLE,
    PersonalConnectionRecord,
    PersonalConnectionRecordKey,
)
from umbod.core.permissions.stores.schema import (
    CAPABILITY_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_TABLE,
    GroupCapabilityPermissionKey,
    GroupCapabilityPermissionRecord,
    GroupConnectorPermissionKey,
    GroupConnectorPermissionRecord,
)
from umbod.core.persistence import (
    Database,
    DeleteQuery,
    NoFilter,
    TransactionMode,
    UpsertCommand,
)
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE


@dataclass(frozen=True)
class RuntimeCase:
    database: Database
    bundle: DownstreamMcpStores
    store: PersonalRuntimeAuthorizationStore
    query: PersonalRuntimeAuthorizationQuery
    grant: PersonalOAuthGrant


async def install_authorization(case: RuntimeCase, authorization: Authorized) -> None:
    connection = await case.bundle.personal_connections.get(case.query.key)
    await case.bundle.personal_connections.replace_authorization(
        ReplacePersonalAuthorization(
            key=case.query.key,
            expected_revision=connection.revision,
            authorization=authorization,
        )
    )


@pytest_asyncio.fixture(params=("inmemory", "sqlite"))
async def runtime_case(request: pytest.FixtureRequest, tmp_path: Path) -> RuntimeCase:
    runtime = (
        await prepared_inmemory_runtime()
        if request.param == "inmemory"
        else await prepared_sqlite_runtime(tmp_path / "runtime.sqlite3")
    )
    bundle = await create_downstream_mcp_stores("runtime-secret", runtime.database)
    definition = OAuthConnectorDefinition(
        connector_id="personal",
        display_name="Personal",
        endpoint_url="https://resource.example/mcp",
        authorization_mode="personal",
    )
    await bundle.definitions.save(SaveConnectorDefinition(definition=definition))
    await bundle.publishing.publish_connector("personal")
    async with runtime.database.session(
        mode=TransactionMode.SERIALIZED_WRITE
    ) as session:
        configuration = await install_personal_oauth_configuration(
            session,
            AuthenticatedTextCipher("runtime-secret"),
            "personal",
            PersonalOAuthSettings(
                requested_scopes=("read", "write"),
                client=PreconfiguredPublicOAuthClient(
                    issuer_url="https://issuer.example", client_id="client"
                ),
            ),
        )
        await session.upsert(
            CONNECTOR_PERMISSION_TABLE,
            UpsertCommand(
                key=GroupConnectorPermissionKey(
                    group_id="team", connector_id="personal"
                ),
                row=GroupConnectorPermissionRecord(
                    group_id="team", connector_id="personal"
                ),
            ),
        )
    key = PersonalConnectionKey(
        principal=CanonicalPrincipal(namespace="trusted", subject="owner"),
        connector_id="personal",
    )
    await bundle.personal_connections.set_enabled(
        SetPersonalConnectionEnabled(key=key, enabled=True)
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    grant = PersonalOAuthGrant(
        version=2,
        key=key,
        issuer="https://issuer.example",
        resource=definition.endpoint_url,
        client_id="client",
        token_endpoint="https://issuer.example/token",
        redirect_uri="https://umbod.example/callback",
        client_mode="preconfigured_public",
        token_endpoint_auth_method="none",
        requested_scopes=("read", "write"),
        granted_scopes=("read",),
        configuration_revision=configuration.policy.revision,
        issued_at=now,
        lifetime=ExpiringPersonalToken(expires_at=now + timedelta(hours=1)),
        access_token=SecretStr("owner-token"),
        refresh_token=AbsentPersonalRefreshToken(),
    )
    case = RuntimeCase(
        database=runtime.database,
        bundle=bundle,
        store=bundle.personal_runtime_authorizations,
        query=PersonalRuntimeAuthorizationQuery(key=key, group_ids=("team",), now=now),
        grant=grant,
    )
    await install_authorization(case, authorize_personal_grant(grant))
    return case


@pytest.mark.asyncio
async def test_resolution_survives_store_recreation_without_resetting_expiry(
    runtime_case: RuntimeCase,
) -> None:
    first = await runtime_case.store.resolve(runtime_case.query)
    recreated = await create_downstream_mcp_stores(
        "runtime-secret", runtime_case.database
    )
    second = await recreated.personal_runtime_authorizations.resolve(
        runtime_case.query.model_copy(
            update={"now": runtime_case.query.now + timedelta(minutes=30)}
        )
    )
    assert second == first
    assert second.access_token.get_secret_value() == "owner-token"
    assert second.expires_at == runtime_case.query.now + timedelta(hours=1)
    assert "owner-token" not in second.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("versioned", (True, False))
async def test_missing_policy_uses_legacy_defaults_but_requires_versioned_grant(
    runtime_case: RuntimeCase, versioned: bool
) -> None:
    async with runtime_case.database.session(
        mode=TransactionMode.SERIALIZED_WRITE
    ) as session:
        await session.delete(
            PERSONAL_OAUTH_CONFIGURATION_TABLE, DeleteQuery(NoFilter())
        )
    grant = runtime_case.grant.model_copy(
        update={
            "configuration_revision": "legacy",
            "client_mode": "dynamic_public",
            "requested_scopes": (),
            "granted_scopes": (),
        }
    )
    authorization = authorize_personal_grant(grant)
    if not versioned:
        payload = json.loads(authorization.authorization.get_secret_value())
        del payload["version"]
        authorization = Authorized(authorization=SecretStr(json.dumps(payload)))
    await install_authorization(runtime_case, authorization)
    if not versioned:
        with pytest.raises(PersonalRuntimeUnavailable):
            await runtime_case.store.resolve(runtime_case.query)
        return
    target = await runtime_case.store.resolve(runtime_case.query)
    assert target.configuration_revision == "legacy"
    assert target.access_token == grant.access_token
    assert target.expires_at == runtime_case.query.now + timedelta(hours=1)


@pytest.mark.asyncio
async def test_owners_have_independent_authorizations(
    runtime_case: RuntimeCase,
) -> None:
    key = runtime_case.query.key.model_copy(
        update={"principal": CanonicalPrincipal(namespace="trusted", subject="other")}
    )
    query = runtime_case.query.model_copy(update={"key": key})
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(query)
    connection = await runtime_case.bundle.personal_connections.set_enabled(
        SetPersonalConnectionEnabled(key=key, enabled=True)
    )
    grant = runtime_case.grant.model_copy(
        update={"key": key, "access_token": SecretStr("other-token")}
    )
    await runtime_case.bundle.personal_connections.replace_authorization(
        ReplacePersonalAuthorization(
            key=key,
            expected_revision=connection.revision,
            authorization=authorize_personal_grant(grant),
        )
    )
    assert (
        await runtime_case.store.resolve(query)
    ).access_token.get_secret_value() == "other-token"
    assert (
        await runtime_case.store.resolve(runtime_case.query)
    ).access_token.get_secret_value() == "owner-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "expired",
        "zero",
        "future",
        "unknown",
        "key",
        "resource",
        "policy",
        "scopes",
        "client",
        "issuer",
        "method",
    ],
)
async def test_invalid_grant_binding_and_lifetime_are_denied(
    runtime_case: RuntimeCase, change: str
) -> None:
    now = runtime_case.query.now
    changes: dict[str, dict[str, object]] = {
        "expired": {
            "issued_at": now - timedelta(hours=2),
            "lifetime": ExpiringPersonalToken(expires_at=now - timedelta(hours=1)),
        },
        "zero": {"lifetime": ExpiringPersonalToken(expires_at=now)},
        "future": {"issued_at": now + timedelta(seconds=1)},
        "unknown": {"lifetime": UnknownPersonalTokenLifetime()},
        "key": {
            "key": runtime_case.query.key.model_copy(
                update={
                    "principal": CanonicalPrincipal(
                        namespace="trusted", subject="other"
                    )
                }
            )
        },
        "resource": {"resource": "https://other.example/mcp"},
        "policy": {"configuration_revision": "stale"},
        "scopes": {"requested_scopes": ("read",)},
        "client": {"client_id": "other"},
        "issuer": {"issuer": "https://other.example"},
        "method": {
            "client_mode": "preconfigured_confidential",
            "token_endpoint_auth_method": "client_secret_post",
        },
    }
    await install_authorization(
        runtime_case,
        authorize_personal_grant(runtime_case.grant.model_copy(update=changes[change])),
    )
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(runtime_case.query)


@pytest.mark.asyncio
async def test_unversioned_grant_requires_reconnect(runtime_case: RuntimeCase) -> None:
    raw = json.loads(
        authorize_personal_grant(runtime_case.grant).authorization.get_secret_value()
    )
    del raw["version"]
    await install_authorization(
        runtime_case, Authorized(authorization=SecretStr(json.dumps(raw)))
    )
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(runtime_case.query)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        "{}",
        '{"access_token":"legacy-token","expires_in":3600}',
        '{"version":1}',
        "[]",
    ],
)
async def test_opaque_legacy_and_malformed_authorization_is_preserved_but_denied(
    runtime_case: RuntimeCase, raw: str
) -> None:
    await install_authorization(runtime_case, Authorized(authorization=SecretStr(raw)))
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(runtime_case.query)
    connection = await runtime_case.bundle.personal_connections.get(
        runtime_case.query.key
    )
    assert isinstance(connection.authorization, Authorized)
    assert connection.authorization.authorization.get_secret_value() == raw


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing", ["definition", "configuration", "publication", "grant", "connection"]
)
async def test_missing_current_admission_state_denies(
    runtime_case: RuntimeCase, missing: str
) -> None:
    async with runtime_case.database.session(
        mode=TransactionMode.SERIALIZED_WRITE
    ) as session:
        if missing == "definition":
            await session.delete(CONNECTOR_DEFINITION_TABLE, DeleteQuery(NoFilter()))
        elif missing == "configuration":
            await session.delete(
                PERSONAL_OAUTH_CONFIGURATION_TABLE, DeleteQuery(NoFilter())
            )
        elif missing == "publication":
            await session.delete(PUBLICATION_STATE_TABLE, DeleteQuery(NoFilter()))
        elif missing == "grant":
            await session.delete(CONNECTOR_PERMISSION_TABLE, DeleteQuery(NoFilter()))
        else:
            await session.delete(PERSONAL_CONNECTION_TABLE, DeleteQuery(NoFilter()))
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(runtime_case.query)


@pytest.mark.asyncio
@pytest.mark.parametrize("groups", [(), ("unverified-team",)])
async def test_only_supplied_verified_groups_may_supply_grants(
    runtime_case: RuntimeCase, groups: tuple[str, ...]
) -> None:
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(
            runtime_case.query.model_copy(update={"group_ids": groups})
        )


@pytest.mark.asyncio
async def test_capability_grant_does_not_substitute_for_connector_grant(
    runtime_case: RuntimeCase,
) -> None:
    async with runtime_case.database.session(
        mode=TransactionMode.SERIALIZED_WRITE
    ) as session:
        await session.delete(CONNECTOR_PERMISSION_TABLE, DeleteQuery(NoFilter()))
        await session.upsert(
            CAPABILITY_PERMISSION_TABLE,
            UpsertCommand(
                key=GroupCapabilityPermissionKey(
                    group_id="team",
                    connector_id="personal",
                    capability_kind="tool",
                    capability_key="read",
                ),
                row=GroupCapabilityPermissionRecord(
                    group_id="team",
                    connector_id="personal",
                    capability_kind="tool",
                    capability_key="read",
                ),
            ),
        )
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(runtime_case.query)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transition", ["disable", "disconnect", "policy", "unpublish", "endpoint", "shared"]
)
async def test_current_policy_and_owner_revocations_deny(
    runtime_case: RuntimeCase, transition: str
) -> None:
    if transition == "unpublish":
        await runtime_case.bundle.publishing.unpublish_connector("personal")
    elif transition in ("endpoint", "shared"):
        definition = OAuthConnectorDefinition(
            connector_id="personal",
            display_name="Personal",
            endpoint_url="https://changed.example/mcp"
            if transition == "endpoint"
            else "https://resource.example/mcp",
            authorization_mode="shared" if transition == "shared" else "personal",
        )
        await runtime_case.bundle.definitions.save(
            SaveConnectorDefinition(definition=definition)
        )
    elif transition == "disable":
        await runtime_case.bundle.personal_connections.set_enabled(
            SetPersonalConnectionEnabled(key=runtime_case.query.key, enabled=False)
        )
    elif transition == "disconnect":
        await runtime_case.bundle.personal_connections.disconnect(
            runtime_case.query.key
        )
    else:
        configuration = await runtime_case.bundle.personal_oauth_configurations.get(
            PersonalOAuthConfigurationQuery(connector_id="personal")
        )
        await runtime_case.bundle.personal_oauth_configurations.replace(
            ReplacePersonalOAuthConfiguration(
                connector_id="personal",
                expected_revision=configuration.policy.revision,
                settings=PersonalOAuthSettings(
                    requested_scopes=("read",), client=configuration.policy.client
                ),
            )
        )
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(runtime_case.query)


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["owner", "cipher"])
async def test_encrypted_owner_transplant_and_wrong_cipher_deny(
    runtime_case: RuntimeCase, corruption: str
) -> None:
    key = runtime_case.query.key
    state = await runtime_case.bundle.personal_connections.get(key)
    payload = state.model_dump(mode="json")
    payload["authorization"]["authorization"] = authorize_personal_grant(
        runtime_case.grant
    ).authorization.get_secret_value()
    if corruption == "owner":
        payload["key"]["principal"]["subject"] = "other"
    cipher = AuthenticatedTextCipher(
        "wrong-secret" if corruption == "cipher" else "runtime-secret"
    )
    async with runtime_case.database.session(
        mode=TransactionMode.SERIALIZED_WRITE
    ) as session:
        await session.upsert(
            PERSONAL_CONNECTION_TABLE,
            UpsertCommand(
                key=PersonalConnectionRecordKey(
                    namespace=key.principal.namespace,
                    subject=key.principal.subject,
                    connector_id=key.connector_id,
                ),
                row=PersonalConnectionRecord(
                    namespace=key.principal.namespace,
                    subject=key.principal.subject,
                    connector_id=key.connector_id,
                    document=cipher.encrypt(json.dumps(payload)),
                ),
            ),
        )
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime_case.store.resolve(runtime_case.query)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("access_token", "bad token"),
        ("granted_scopes", ["unapproved"]),
        ("requested_scopes", ["read", "read"]),
        ("refresh_token", {"kind": "present", "token": "\n"}),
        ("lifetime", {"kind": "expiring", "expires_at": "bad-date"}),
    ],
)
def test_grant_validation_rejects_malformed_tokens_scopes_and_expiry(
    field: str, value: object
) -> None:
    raw: dict[str, object] = dict(
        version=2,
        key={
            "principal": {"namespace": "trusted", "subject": "owner"},
            "connector_id": "personal",
        },
        issuer="https://issuer.example",
        resource="https://resource.example/mcp",
        client_id="client",
        token_endpoint="https://issuer.example/token",
        redirect_uri="https://umbod.example/callback",
        client_mode="preconfigured_public",
        token_endpoint_auth_method="none",
        requested_scopes=["read"],
        granted_scopes=["read"],
        configuration_revision="revision",
        issued_at="2026-01-01T00:00:00Z",
        lifetime={"kind": "unknown"},
        access_token="token",
        refresh_token={"kind": "absent"},
    )
    raw[field] = value
    with pytest.raises(ValidationError):
        PersonalOAuthGrant.model_validate(raw)
