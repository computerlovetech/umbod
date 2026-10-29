import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import GenericRoute, PresentCallbackIssuer

from pydantic import BaseModel

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.management import (
    DeleteDownstreamConnectorAggregate,
)
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import (
    PersonalOAuthSettings, DynamicPublicOAuthClient, PreconfiguredConfidentialOAuthClient,
    PersonalOAuthConfigurationQuery, ReplacePersonalOAuthConfiguration,
    PersonalOAuthConfigurationConflict, PersonalOAuthConfigurationUnavailable,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configurations import EncryptedPersonalOAuthConfigurationStore
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configuration_schema import (
    PERSONAL_OAUTH_CONFIGURATION_TABLE, PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID,
    PersonalOAuthConfigurationKey, PersonalOAuthConfigurationRecord,
)
from umbod.core.connectors.downstream_mcp.personal_connections.models import (
    Authorized,
    CanonicalPrincipal,
    PersonalConnection,
    PersonalConnectionKey,
    ReplacePersonalAuthorization,
    SetPersonalConnectionEnabled,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import (
    ClaimPersonalOAuthAttempt,
    CompletePersonalOAuthAttempt,
    FailPersonalOAuthAttempt,
    PersonalOAuthAttemptQuery,
    PersonalOAuthAttemptView,
    PersonalOAuthConflict,
    PersonalOAuthUnavailable,
    PreparePersonalOAuth,
    PreparedPersonalOAuth,
    PublishPersonalOAuthAttempt,
    ReservePersonalOAuthAttempt,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import (
    PersonalOAuthAttemptStore,
)
from umbod.core.connectors.downstream_mcp.stores import (
    DownstreamMcpStores,
    ConnectorIdQuery,
    SaveConnectorDefinition,
    create_downstream_mcp_stores,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_attempts import (
    EncryptedPersonalOAuthAttemptStore,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_schema import (
    PERSONAL_OAUTH_ATTEMPT_TABLE,
    PersonalOAuthAttemptKey,
)
from umbod.core.permissions.stores.schema import (
    CONNECTOR_PERMISSION_TABLE,
    GroupConnectorPermissionKey,
    GroupConnectorPermissionRecord,
)
from umbod.core.persistence import (
    AllFields,
    Database,
    DatabaseSession,
    ReadSession,
    Table,
    DeleteQuery,
    Equals,
    NoFilter,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


@dataclass
class ControlledClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


@dataclass(frozen=True)
class AttemptCase:
    database: Database
    clock: ControlledClock
    bundle: DownstreamMcpStores
    store: PersonalOAuthAttemptStore
    command: ReservePersonalOAuthAttempt
    query: PersonalOAuthAttemptQuery


@pytest_asyncio.fixture(params=("inmemory", "sqlite"))
async def case(request: pytest.FixtureRequest, tmp_path: Path) -> AttemptCase:
    runtime = (
        await prepared_inmemory_runtime()
        if request.param == "inmemory"
        else await prepared_sqlite_runtime(tmp_path / "oauth.sqlite3")
    )
    bundle = await create_downstream_mcp_stores("test-secret", runtime.database)
    definition = OAuthConnectorDefinition(
        connector_id="personal",
        display_name="Personal",
        endpoint_url="https://personal.example/mcp",
        authorization_mode="personal",
    )
    await bundle.definitions.save(SaveConnectorDefinition(definition=definition))
    await bundle.publishing.publish_connector(definition.connector_id)
    async with runtime.database.session(
        mode=TransactionMode.SERIALIZED_WRITE
    ) as session:
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
    current = await bundle.personal_connections.set_enabled(
        SetPersonalConnectionEnabled(key=key, enabled=True)
    )
    assert isinstance(current, PersonalConnection)
    now = datetime.now(UTC)
    attempt_id = uuid4().hex
    command = ReservePersonalOAuthAttempt(
        key=key,
        attempt_id=attempt_id,
        expected_revision=current.revision,
        definition_fingerprint=hashlib.sha256(
            json.dumps(
                definition.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        endpoint_url=definition.endpoint_url,
        group_ids=("team",),
        preparation=PreparePersonalOAuth(
            endpoint_url=definition.endpoint_url,
            redirect_uri="https://umbod.example/api/oauth/downstream-mcp/callback",
            state=attempt_id + ".unpredictable-state-secret",
            code_verifier="private-pkce-verifier",
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    clock = ControlledClock(now=now)
    return AttemptCase(
        database=runtime.database,
        clock=clock,
        bundle=bundle,
        store=EncryptedPersonalOAuthAttemptStore(
            runtime.database, AuthenticatedTextCipher("test-secret"), clock
        ),
        command=command,
        query=PersonalOAuthAttemptQuery(key=key, attempt_id=attempt_id, now=now),
    )


def publication(case: AttemptCase) -> PublishPersonalOAuthAttempt:
    return PublishPersonalOAuthAttempt(
        query=case.query,
        prepared=PreparedPersonalOAuth(
            authorization_url="https://issuer.example/authorize?private=url",
            context="private-provider-context",
        ),
    )


def claim_command(case: AttemptCase) -> ClaimPersonalOAuthAttempt:
    return ClaimPersonalOAuthAttempt(
        route=GenericRoute(kind="generic"), issuer=PresentCallbackIssuer(kind="present", value="https://issuer.example"), state=case.command.preparation.state,
        claim_id="exclusive-claim",
        now=case.query.now,
    )


def completion(case: AttemptCase) -> CompletePersonalOAuthAttempt:
    return CompletePersonalOAuthAttempt(
        query=case.query,
        claim_id="exclusive-claim",
        authorization=Authorized(authorization="private-new-authorization"),
    )


async def pending(case: AttemptCase) -> None:
    await case.store.reserve(case.command)
    await case.store.publish(publication(case))


@pytest.mark.asyncio
async def test_attempt_survives_adapter_recreation_and_completes_atomically(
    case: AttemptCase,
) -> None:
    assert (await case.store.reserve(case.command)).status == "preparing"
    second = await create_downstream_mcp_stores("test-secret", case.database)
    assert (
        await second.personal_oauth_attempts.publish(publication(case))
    ).status == "pending"
    claimed = await second.personal_oauth_attempts.claim(claim_command(case))
    assert claimed.preparation == case.command.preparation
    assert claimed.prepared == publication(case).prepared
    assert (await case.store.complete(completion(case))).status == "completed"
    state = await second.personal_connections.get(case.query.key)
    assert isinstance(state, PersonalConnection)
    assert state.authorization == completion(case).authorization
    with pytest.raises(PersonalOAuthUnavailable):
        await second.personal_oauth_attempts.complete(completion(case))


@pytest.mark.asyncio
async def test_sqlite_attempt_finishes_through_recreated_database_runtime(
    case: AttemptCase, tmp_path: Path
) -> None:
    database_path = tmp_path / "oauth.sqlite3"
    if not database_path.exists():
        pytest.skip("SQLite-specific process-independent persistence contract")
    await pending(case)
    runtime = await prepared_sqlite_runtime(database_path)
    restored = await create_downstream_mcp_stores("test-secret", runtime.database)
    attempt = await restored.personal_oauth_attempts.claim(claim_command(case))
    assert attempt.preparation == case.command.preparation
    assert (
        await restored.personal_oauth_attempts.complete(completion(case))
    ).status == "completed"
    state = await case.bundle.personal_connections.get(case.query.key)
    assert isinstance(state, PersonalConnection)
    assert state.authorization == completion(case).authorization


@pytest.mark.asyncio
async def test_competing_reservations_have_one_winner(case: AttemptCase) -> None:
    second = await create_downstream_mcp_stores("test-secret", case.database)
    results = await asyncio.gather(
        case.store.reserve(case.command),
        second.personal_oauth_attempts.reserve(case.command),
        return_exceptions=True,
    )
    assert sum(isinstance(result, PersonalOAuthAttemptView) for result in results) == 1
    assert sum(isinstance(result, PersonalOAuthConflict) for result in results) == 1


@pytest.mark.asyncio
async def test_independent_callbacks_claim_at_most_once(case: AttemptCase) -> None:
    await pending(case)
    second = await create_downstream_mcp_stores("test-secret", case.database)
    results = await asyncio.gather(
        case.store.claim(claim_command(case)),
        second.personal_oauth_attempts.claim(claim_command(case)),
        return_exceptions=True,
    )
    assert sum(isinstance(result, PersonalOAuthUnavailable) for result in results) == 1
    assert (await case.store.get(case.query)).status == "exchanging"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ("subject", "namespace", "connector_id"))
@pytest.mark.parametrize("operation", ("get", "cancel", "abort", "complete", "fail"))
async def test_wrong_owner_cannot_read_or_mutate_attempt(
    case: AttemptCase, field: str, operation: str
) -> None:
    await pending(case)
    await case.store.claim(claim_command(case))
    key = case.query.key
    other_key = (
        key.model_copy(update={field: "other"})
        if field == "connector_id"
        else key.model_copy(
            update={"principal": key.principal.model_copy(update={field: "other"})}
        )
    )
    query = case.query.model_copy(update={"key": other_key})
    with pytest.raises(PersonalOAuthUnavailable):
        if operation == "get":
            await case.store.get(query)
        elif operation == "cancel":
            await case.store.cancel(query)
        elif operation == "abort":
            await case.store.abort_preparation(query)
        elif operation == "complete":
            await case.store.complete(
                completion(case).model_copy(update={"query": query})
            )
        else:
            await case.store.fail(
                FailPersonalOAuthAttempt(query=query, claim_id="exclusive-claim")
            )
    assert (await case.store.get(case.query)).status == "exchanging"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state", ("missing", "unknown.secret", "wrong-secret", "empty-secret")
)
async def test_invalid_state_never_consumes_attempt(
    case: AttemptCase, state: str
) -> None:
    await pending(case)
    value = (
        case.command.attempt_id + ".wrong"
        if state == "wrong-secret"
        else case.command.attempt_id + "."
        if state == "empty-secret"
        else state
    )
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.claim(
            claim_command(case).model_copy(
                update={
                    "state": PreparePersonalOAuth(
                        endpoint_url="x",
                        redirect_uri="x",
                        state=value,
                        code_verifier="x",
                    ).state
                }
            )
        )
    assert (await case.store.get(case.query)).status == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ("preparing", "pending", "exchanging"))
async def test_expiration_allows_fresh_reservation_and_bounds_history(
    case: AttemptCase, phase: str
) -> None:
    await case.store.reserve(case.command)
    if phase != "preparing":
        await case.store.publish(publication(case))
    if phase == "exchanging":
        await case.store.claim(claim_command(case))
    expired = case.query.model_copy(update={"now": case.command.expires_at})
    assert (await case.store.get(expired)).status == "expired"
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.claim(
            claim_command(case).model_copy(update={"now": expired.now})
        )
    attempt_id = uuid4().hex
    fresh = case.command.model_copy(
        update={
            "attempt_id": attempt_id,
            "created_at": expired.now,
            "expires_at": expired.now + timedelta(minutes=5),
            "preparation": case.command.preparation.model_copy(
                update={
                    "state": PreparePersonalOAuth(
                        endpoint_url="x",
                        redirect_uri="x",
                        state=attempt_id + ".fresh-secret",
                        code_verifier="x",
                    ).state
                }
            ),
        }
    )
    assert (await case.store.reserve(fresh)).status == "preparing"
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.get(expired)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ("preparing", "pending", "exchanging"))
async def test_cancellation_prevents_publish_claim_and_installation(
    case: AttemptCase, phase: str
) -> None:
    await case.store.reserve(case.command)
    if phase != "preparing":
        await case.store.publish(publication(case))
    if phase == "exchanging":
        await case.store.claim(claim_command(case))
    previous = await case.bundle.personal_connections.get(case.query.key)
    assert (await case.store.cancel(case.query)).status == "cancelled"
    for operation in (
        case.store.publish(publication(case)),
        case.store.claim(claim_command(case)),
        case.store.complete(completion(case)),
    ):
        with pytest.raises(PersonalOAuthUnavailable):
            await operation
    assert await case.bundle.personal_connections.get(case.query.key) == previous


async def withdraw(case: AttemptCase, change: str) -> None:
    if change == "disable":
        await case.bundle.personal_connections.set_enabled(
            SetPersonalConnectionEnabled(key=case.query.key, enabled=False)
        )
    elif change == "disconnect":
        await case.bundle.personal_connections.disconnect(case.query.key)
    elif change == "revision":
        await case.bundle.personal_connections.replace_authorization(
            ReplacePersonalAuthorization(
                key=case.query.key,
                expected_revision=case.command.expected_revision,
                authorization=Authorized(authorization="existing-authorization"),
            )
        )
    elif change == "unpublish":
        await case.bundle.publishing.unpublish_connector(case.query.key.connector_id)
    elif change == "grants":
        async with case.database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            await session.delete(CONNECTOR_PERMISSION_TABLE, DeleteQuery(NoFilter()))
    elif change == "delete":
        await case.bundle.unit_of_work.delete(
            DeleteDownstreamConnectorAggregate(connector_id=case.query.key.connector_id)
        )
    else:
        definition = OAuthConnectorDefinition(
            connector_id="personal",
            display_name="Changed",
            endpoint_url="https://personal.example/mcp",
            authorization_mode="personal" if change == "fingerprint" else "shared",
        )
        await case.bundle.definitions.save(
            SaveConnectorDefinition(definition=definition)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    (
        "disable",
        "disconnect",
        "revision",
        "unpublish",
        "grants",
        "delete",
        "fingerprint",
        "shared",
    ),
)
@pytest.mark.parametrize("phase", ("reserve", "publish", "claim", "complete"))
async def test_every_transition_rechecks_atomic_eligibility(
    case: AttemptCase, change: str, phase: str
) -> None:
    if phase != "reserve":
        await case.store.reserve(case.command)
    if phase in ("claim", "complete"):
        await case.store.publish(publication(case))
    if phase == "complete":
        await case.store.claim(claim_command(case))
    await withdraw(case, change)
    previous = await case.bundle.personal_connections.get(case.query.key)
    with pytest.raises(PersonalOAuthUnavailable):
        if phase == "reserve":
            await case.store.reserve(case.command)
        elif phase == "publish":
            await case.store.publish(publication(case))
        elif phase == "claim":
            await case.store.claim(claim_command(case))
        else:
            await case.store.complete(completion(case))
    assert await case.bundle.personal_connections.get(case.query.key) == previous
    if change == "delete":
        with pytest.raises(PersonalOAuthUnavailable):
            await case.store.get(case.query)
    elif phase != "reserve":
        assert (await case.store.cancel(case.query)).status == "cancelled"


@pytest.mark.asyncio
async def test_fail_only_matches_exchanging_claim_and_abort_only_preparing(
    case: AttemptCase,
) -> None:
    await pending(case)
    await case.store.abort_preparation(case.query)
    await case.store.fail(
        FailPersonalOAuthAttempt(query=case.query, claim_id="exclusive-claim")
    )
    assert (await case.store.get(case.query)).status == "pending"
    await case.store.claim(claim_command(case))
    await case.store.fail(FailPersonalOAuthAttempt(query=case.query, claim_id="wrong"))
    assert (await case.store.get(case.query)).status == "exchanging"
    await case.store.abort_preparation(case.query)
    assert (await case.store.get(case.query)).status == "exchanging"
    await case.store.fail(
        FailPersonalOAuthAttempt(query=case.query, claim_id="exclusive-claim")
    )
    assert (await case.store.get(case.query)).status == "failed"


@pytest.mark.asyncio
async def test_preparation_abortion_is_terminal(case: AttemptCase) -> None:
    await case.store.reserve(case.command)
    await case.store.abort_preparation(case.query)
    assert (await case.store.get(case.query)).status == "failed"
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.publish(publication(case))


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ("cancel", "expire", "complete", "fail", "abort"))
async def test_adapter_encrypts_secrets_and_terminal_records_purge_sensitive_context(
    case: AttemptCase, terminal: str
) -> None:
    await case.store.reserve(case.command)
    if terminal != "abort":
        await case.store.publish(publication(case))
    cipher = AuthenticatedTextCipher("test-secret")
    async with case.database.session(mode=TransactionMode.READ_WRITE) as session:
        row = await session.find_one(
            PERSONAL_OAUTH_ATTEMPT_TABLE,
            Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
        )
    assert row is not None
    for secret in (
        "private-pkce-verifier",
        "unpredictable-state-secret",
        "private-provider-context",
        "private=url",
    ):
        assert secret not in row.document
    if terminal == "cancel":
        await case.store.cancel(case.query)
    elif terminal == "expire":
        await case.store.get(
            case.query.model_copy(update={"now": case.command.expires_at})
        )
    elif terminal == "abort":
        await case.store.abort_preparation(case.query)
    else:
        await case.store.claim(claim_command(case))
        if terminal == "complete":
            await case.store.complete(completion(case))
        else:
            await case.store.fail(
                FailPersonalOAuthAttempt(query=case.query, claim_id="exclusive-claim")
            )
    async with case.database.session(mode=TransactionMode.READ_WRITE) as session:
        row = await session.find_one(
            PERSONAL_OAUTH_ATTEMPT_TABLE,
            Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
        )
    assert row is not None
    document = json.loads(cipher.decrypt(row.document))
    assert set(document) == {"key", "attempt_id", "expires_at", "status"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ("namespace", "subject", "connector_id", "attempt_id")
)
async def test_adapter_rejects_decrypted_ownership_tampering(
    case: AttemptCase, field: str
) -> None:
    await pending(case)
    async with case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        row = await session.find_one(
            PERSONAL_OAUTH_ATTEMPT_TABLE,
            Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
        )
        assert row is not None
        copied = row.model_copy(update={field: "tampered"})
        await session.upsert(
            PERSONAL_OAUTH_ATTEMPT_TABLE,
            UpsertCommand(
                key=PersonalOAuthAttemptKey(attempt_id=copied.attempt_id), row=copied
            ),
        )
    query = case.query.model_copy(update={"attempt_id": copied.attempt_id})
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.get(query)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ("reserve", "publish", "complete"))
@pytest.mark.parametrize("delete_first", (True, False))
async def test_aggregate_deletion_racing_transition_leaves_no_orphans(
    case: AttemptCase, phase: str, delete_first: bool
) -> None:
    if phase != "reserve":
        await case.store.reserve(case.command)
    if phase == "complete":
        await case.store.publish(publication(case))
        await case.store.claim(claim_command(case))
    operation = (
        case.store.reserve(case.command)
        if phase == "reserve"
        else case.store.publish(publication(case))
        if phase == "publish"
        else case.store.complete(completion(case))
    )
    deletion = case.bundle.unit_of_work.delete(
        DeleteDownstreamConnectorAggregate(connector_id=case.query.key.connector_id)
    )
    results = await asyncio.gather(
        *((deletion, operation) if delete_first else (operation, deletion)),
        return_exceptions=True,
    )
    assert all(
        result is None
        or isinstance(result, (PersonalOAuthAttemptView, PersonalOAuthUnavailable))
        for result in results
    )
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.get(case.query)
    assert not isinstance(
        await case.bundle.personal_connections.get(case.query.key), PersonalConnection
    )


class LockObservedDatabase:
    def __init__(self, database: Database, waiting: asyncio.Event) -> None:
        self._database = database
        self._waiting = waiting

    async def ensure_schema(
        self, tables: Sequence[Table[BaseModel, BaseModel]]
    ) -> None:
        await self._database.ensure_schema(tables)

    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[ReadSession]:
        async with self._database.read_session() as session:
            yield session

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        self._waiting.set()
        async with self._database.session(mode=mode) as session:
            yield session


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ("publish", "claim", "complete"))
async def test_locked_transition_uses_current_clock_after_waiting(
    case: AttemptCase, phase: str
) -> None:
    await case.store.reserve(case.command)
    if phase != "publish":
        await case.store.publish(publication(case))
    if phase == "complete":
        await case.store.claim(claim_command(case))
    previous = await case.bundle.personal_connections.get(case.query.key)
    waiting = asyncio.Event()
    delayed: PersonalOAuthAttemptStore = EncryptedPersonalOAuthAttemptStore(
        LockObservedDatabase(case.database, waiting),
        AuthenticatedTextCipher("test-secret"),
        case.clock,
    )
    async with case.database.session(mode=TransactionMode.SERIALIZED_WRITE):
        operation = (
            delayed.publish(publication(case))
            if phase == "publish"
            else delayed.claim(claim_command(case))
            if phase == "claim"
            else delayed.complete(completion(case))
        )
        task = asyncio.create_task(operation)
        await asyncio.wait_for(waiting.wait(), timeout=2)
        assert not task.done()
        case.clock.now = case.command.expires_at
    with pytest.raises(PersonalOAuthUnavailable):
        await task
    assert await case.bundle.personal_connections.get(case.query.key) == previous
    assert (await case.store.get(case.query)).status == "expired"


@pytest.mark.asyncio
async def test_exchange_crossing_expiry_cannot_install_with_old_query_time(
    case: AttemptCase,
) -> None:
    await pending(case)
    await case.store.claim(claim_command(case))
    previous = await case.bundle.personal_connections.get(case.query.key)
    case.clock.now = case.command.expires_at
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.complete(completion(case))
    assert await case.bundle.personal_connections.get(case.query.key) == previous
    assert (await case.store.get(case.query)).status == "expired"


class CompletionWriteFailureCipher:
    def __init__(self) -> None:
        self._cipher = AuthenticatedTextCipher("test-secret")

    def encrypt(self, plaintext: str) -> str:
        if '"status": "completed"' in plaintext:
            raise RuntimeError("simulated completion write failure")
        return self._cipher.encrypt(plaintext)

    def decrypt(self, ciphertext: str) -> str:
        return self._cipher.decrypt(ciphertext)


@pytest.mark.asyncio
async def test_completion_write_failure_rolls_back_authorization_installation(
    case: AttemptCase,
) -> None:
    await pending(case)
    await case.store.claim(claim_command(case))
    previous = await case.bundle.personal_connections.get(case.query.key)
    failing: PersonalOAuthAttemptStore = EncryptedPersonalOAuthAttemptStore(
        case.database, CompletionWriteFailureCipher(), case.clock
    )
    with pytest.raises(RuntimeError, match="simulated completion write failure"):
        await failing.complete(completion(case))
    assert await case.bundle.personal_connections.get(case.query.key) == previous
    assert (await case.store.get(case.query)).status == "exchanging"


async def persisted_attempt_document(case: AttemptCase) -> dict[str, object]:
    async with case.database.session(mode=TransactionMode.READ_WRITE) as session:
        row = await session.find_one(
            PERSONAL_OAUTH_ATTEMPT_TABLE,
            Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
        )
    assert row is not None
    return json.loads(AuthenticatedTextCipher("test-secret").decrypt(row.document))


async def advance_to_phase(case: AttemptCase, phase: str) -> None:
    await case.store.reserve(case.command)
    if phase != "publish":
        await case.store.publish(publication(case))
    if phase == "complete":
        await case.store.claim(claim_command(case))


async def transition_attempt(
    case: AttemptCase, store: PersonalOAuthAttemptStore, phase: str
) -> None:
    if phase == "publish":
        await store.publish(publication(case))
    elif phase == "claim":
        await store.claim(claim_command(case))
    else:
        await store.complete(completion(case))


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ("publish", "claim", "complete"))
async def test_expired_transition_commits_sensitive_document_cleanup_before_unavailable(
    case: AttemptCase, phase: str
) -> None:
    await advance_to_phase(case, phase)
    case.clock.now = case.command.expires_at
    with pytest.raises(PersonalOAuthUnavailable):
        await transition_attempt(case, case.store, phase)
    document = await persisted_attempt_document(case)
    assert document["status"] == "expired"
    assert set(document) == {"key", "attempt_id", "expires_at", "status"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    ("get", "cancel", "publish", "complete", "invalid_state", "wrong_claim"),
)
async def test_expired_attempt_is_not_purged_by_wrong_owner_or_invalid_credentials(
    case: AttemptCase, operation: str
) -> None:
    phase = (
        "publish"
        if operation == "publish"
        else "claim"
        if operation == "invalid_state"
        else "complete"
    )
    await advance_to_phase(case, phase)
    before = await persisted_attempt_document(case)
    case.clock.now = case.command.expires_at
    other_key = case.query.key.model_copy(
        update={
            "principal": case.query.key.principal.model_copy(
                update={"subject": "other"}
            )
        }
    )
    other_query = case.query.model_copy(update={"key": other_key})
    with pytest.raises(PersonalOAuthUnavailable):
        if operation == "get":
            await case.store.get(other_query)
        elif operation == "cancel":
            await case.store.cancel(other_query)
        elif operation == "publish":
            await case.store.publish(
                publication(case).model_copy(update={"query": other_query})
            )
        elif operation == "complete":
            await case.store.complete(
                completion(case).model_copy(update={"query": other_query})
            )
        elif operation == "wrong_claim":
            await case.store.complete(
                completion(case).model_copy(update={"claim_id": "wrong"})
            )
        else:
            await case.store.claim(
                ClaimPersonalOAuthAttempt(
                    route=GenericRoute(kind="generic"), issuer=PresentCallbackIssuer(kind="present", value="https://issuer.example"), state=case.command.attempt_id + ".invalid",
                    claim_id="invalid",
                    now=case.query.now,
                )
            )
    assert await persisted_attempt_document(case) == before


class EligibilityAdvancingCipher:
    def __init__(self, clock: ControlledClock, expires_at: datetime) -> None:
        self._cipher = AuthenticatedTextCipher("test-secret")
        self._clock = clock
        self._expires_at = expires_at

    def encrypt(self, plaintext: str) -> str:
        return self._cipher.encrypt(plaintext)

    def decrypt(self, ciphertext: str) -> str:
        plaintext = self._cipher.decrypt(ciphertext)
        if "enabled" in json.loads(plaintext):
            self._clock.now = self._expires_at
        return plaintext


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ("publish", "claim", "complete"))
async def test_expiry_during_awaited_eligibility_commits_cleanup_without_installation(
    case: AttemptCase, phase: str
) -> None:
    await advance_to_phase(case, phase)
    previous = await case.bundle.personal_connections.get(case.query.key)
    advancing: PersonalOAuthAttemptStore = EncryptedPersonalOAuthAttemptStore(
        case.database,
        EligibilityAdvancingCipher(case.clock, case.command.expires_at),
        case.clock,
    )
    with pytest.raises(PersonalOAuthUnavailable):
        await transition_attempt(case, advancing, phase)
    document = await persisted_attempt_document(case)
    assert document["status"] == "expired"
    assert set(document) == {"key", "attempt_id", "expires_at", "status"}
    assert await case.bundle.personal_connections.get(case.query.key) == previous


@pytest.mark.asyncio
async def test_wrong_claim_cannot_complete_and_expired_exchange_cannot_install(
    case: AttemptCase,
) -> None:
    await pending(case)
    await case.store.claim(claim_command(case))
    previous = await case.bundle.personal_connections.get(case.query.key)
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.complete(
            completion(case).model_copy(update={"claim_id": "wrong"})
        )
    with pytest.raises(PersonalOAuthUnavailable):
        await case.store.complete(
            completion(case).model_copy(
                update={
                    "query": case.query.model_copy(
                        update={"now": case.command.expires_at}
                    )
                }
            )
        )
    assert await case.bundle.personal_connections.get(case.query.key) == previous
    assert (
        await case.store.get(
            case.query.model_copy(update={"now": case.command.expires_at})
        )
    ).status == "expired"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("cancel", "fail"))
async def test_previous_authorization_survives_failed_reauthorization(
    case: AttemptCase, operation: str
) -> None:
    previous = await case.bundle.personal_connections.replace_authorization(
        ReplacePersonalAuthorization(
            key=case.query.key,
            expected_revision=case.command.expected_revision,
            authorization=Authorized(authorization="previous-authorization"),
        )
    )
    assert isinstance(previous, PersonalConnection)
    await case.store.reserve(
        case.command.model_copy(update={"expected_revision": previous.revision})
    )
    await case.store.publish(publication(case))
    await case.store.claim(claim_command(case))
    if operation == "cancel":
        await case.store.cancel(case.query)
    else:
        await case.store.fail(
            FailPersonalOAuthAttempt(query=case.query, claim_id="exclusive-claim")
        )
    assert await case.bundle.personal_connections.get(case.query.key) == previous


def confidential_settings() -> PersonalOAuthSettings:
    return PersonalOAuthSettings(
        requested_scopes=("documents.read",),
        client=PreconfiguredConfidentialOAuthClient(
            issuer_url="https://issuer.example", client_id="configured-client",
            client_secret="configured-client-secret", token_endpoint_auth_method="client_secret_basic",
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ("preparing", "pending", "exchanging", "completed"))
async def test_policy_rotation_erases_authority_and_attempts_preserving_enablement(
    case: AttemptCase, stage: str,
) -> None:
    configurations = case.bundle.personal_oauth_configurations
    configured = await configurations.replace(ReplacePersonalOAuthConfiguration(
        connector_id="personal", expected_revision="legacy", settings=confidential_settings(),
    ))
    current = await case.bundle.personal_connections.get(case.query.key)
    assert isinstance(current, PersonalConnection)
    command = case.command.model_copy(update={
        "expected_revision": current.revision,
        "preparation": case.command.preparation.model_copy(update={"policy": configured.policy}),
    })
    active = replace(case, command=command)
    await active.store.reserve(command)
    if stage != "preparing":
        await active.store.publish(publication(active))
    if stage in ("exchanging", "completed"):
        await active.store.claim(claim_command(active))
    if stage == "completed":
        await active.store.complete(completion(active))
    replacement = await configurations.replace(ReplacePersonalOAuthConfiguration(
        connector_id="personal", expected_revision=configured.policy.revision,
        settings=PersonalOAuthSettings(requested_scopes=(), client=DynamicPublicOAuthClient()),
    ))
    connection = await case.bundle.personal_connections.get(case.query.key)
    assert connection.enabled is True
    assert connection.authorization.kind == "unauthorized"
    assert connection.revision != current.revision
    assert replacement.policy.revision != configured.policy.revision
    with pytest.raises(PersonalOAuthUnavailable):
        await active.store.complete(completion(active))
    with pytest.raises(PersonalOAuthUnavailable):
        await active.store.get(case.query)
    async with case.database.session(mode=TransactionMode.READ_WRITE) as session:
        row = await session.find_one(PERSONAL_OAUTH_CONFIGURATION_TABLE, Query(filter=Equals(PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID, "personal"), projection=AllFields(), ordering=Unordered()))
    assert row is not None
    plaintext = AuthenticatedTextCipher("test-secret").decrypt(row.document)
    assert "configured-client-secret" not in plaintext
    assert "client_secret" not in plaintext


@pytest.mark.asyncio
async def test_configured_secret_is_encrypted_bound_and_survives_adapter_recreation(case: AttemptCase) -> None:
    configured = await case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
        connector_id="personal", expected_revision="legacy", settings=confidential_settings(),
    ))
    recreated = await create_downstream_mcp_stores("test-secret", case.database)
    query = PersonalOAuthConfigurationQuery(connector_id="personal")
    assert await recreated.personal_oauth_configurations.get(query) == configured
    async with case.database.session(mode=TransactionMode.READ_WRITE) as session:
        row = await session.find_one(PERSONAL_OAUTH_CONFIGURATION_TABLE, Query(filter=Equals(PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID, "personal"), projection=AllFields(), ordering=Unordered()))
    assert row is not None
    assert "configured-client-secret" not in row.document
    definition = await case.bundle.definitions.get(ConnectorIdQuery(connector_id="personal"))
    assert "configured-client-secret" not in definition.definition.model_dump_json()
    wrong = await create_downstream_mcp_stores("wrong-secret", case.database)
    with pytest.raises(PersonalOAuthConfigurationUnavailable):
        await wrong.personal_oauth_configurations.get(query)


@pytest.mark.asyncio
async def test_competing_policy_changes_compare_revisions(case: AttemptCase) -> None:
    commands = tuple(ReplacePersonalOAuthConfiguration(
        connector_id="personal", expected_revision="legacy",
        settings=PersonalOAuthSettings(requested_scopes=(scope,), client=DynamicPublicOAuthClient()),
    ) for scope in ("read", "write"))
    results = await asyncio.gather(*(case.bundle.personal_oauth_configurations.replace(command) for command in commands), return_exceptions=True)
    assert sum(isinstance(result, PersonalOAuthConfigurationConflict) for result in results) == 1
    assert sum(not isinstance(result, BaseException) for result in results) == 1


@pytest.mark.asyncio
async def test_unchanged_public_policy_preserves_authorization_and_active_attempt(case: AttemptCase) -> None:
    await pending(case)
    result = await case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
        connector_id="personal", expected_revision="legacy",
        settings=PersonalOAuthSettings(requested_scopes=(), client=DynamicPublicOAuthClient()),
    ))
    assert result.policy.revision == "legacy"
    assert (await case.store.get(case.query)).status == "pending"
    assert (await case.bundle.personal_connections.get(case.query.key)).revision == case.command.expected_revision


class FailingPolicyCipher:
    def encrypt(self, plaintext: str) -> str:
        if "policy" in json.loads(plaintext):
            raise RuntimeError("injected policy write failure")
        return AuthenticatedTextCipher("test-secret").encrypt(plaintext)

    def decrypt(self, ciphertext: str) -> str:
        return AuthenticatedTextCipher("test-secret").decrypt(ciphertext)


@pytest.mark.asyncio
async def test_policy_failure_rolls_back_attempt_and_connection_invalidation(case: AttemptCase) -> None:
    await pending(case)
    store = EncryptedPersonalOAuthConfigurationStore(case.database, FailingPolicyCipher())
    with pytest.raises(RuntimeError, match="injected policy"):
        await store.replace(ReplacePersonalOAuthConfiguration(
            connector_id="personal", expected_revision="legacy", settings=confidential_settings(),
        ))
    assert (await case.store.get(case.query)).status == "pending"
    assert (await case.bundle.personal_connections.get(case.query.key)).revision == case.command.expected_revision
    assert (await case.bundle.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="personal"))).policy.revision == "legacy"


@pytest.mark.asyncio
async def test_encrypted_policy_cannot_be_transplanted_to_another_connector(case: AttemptCase) -> None:
    configured = await case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
        connector_id="personal", expected_revision="legacy", settings=confidential_settings(),
    ))
    await case.bundle.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
        connector_id="other", display_name="Other", endpoint_url="https://other.example/mcp", authorization_mode="personal",
    )))
    async with case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        row = await session.find_one(PERSONAL_OAUTH_CONFIGURATION_TABLE, Query(filter=Equals(PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID, "personal"), projection=AllFields(), ordering=Unordered()))
        assert row is not None
        await session.upsert(PERSONAL_OAUTH_CONFIGURATION_TABLE, UpsertCommand(
            key=PersonalOAuthConfigurationKey(connector_id="other"),
            row=PersonalOAuthConfigurationRecord(connector_id="other", revision=configured.policy.revision, document=row.document),
        ))
    with pytest.raises(PersonalOAuthConfigurationUnavailable):
        await case.bundle.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="other"))
    assert await case.bundle.personal_oauth_configurations.get(PersonalOAuthConfigurationQuery(connector_id="personal")) == configured


@pytest.mark.asyncio
async def test_deleted_connector_configuration_cannot_be_recreated(case: AttemptCase) -> None:
    configuration = await case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
        connector_id="personal", expected_revision="legacy", settings=confidential_settings(),
    ))
    await case.bundle.unit_of_work.delete(DeleteDownstreamConnectorAggregate(connector_id="personal"))
    with pytest.raises(PersonalOAuthConfigurationUnavailable):
        await case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
            connector_id="personal", expected_revision=configuration.policy.revision, settings=confidential_settings(),
        ))
    async with case.database.session(mode=TransactionMode.READ_WRITE) as session:
        assert await session.find_one(PERSONAL_OAUTH_CONFIGURATION_TABLE, Query(filter=Equals(PERSONAL_OAUTH_CONFIGURATION_CONNECTOR_ID, "personal"), projection=AllFields(), ordering=Unordered())) is None
