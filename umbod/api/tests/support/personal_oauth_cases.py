import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal.connections.models import (
    Authorized,
    CanonicalPrincipal,
    PersonalConnection,
    PersonalConnectionKey,
    SetPersonalConnectionEnabled,
)
from umbod.core.connectors.downstream_mcp.personal.oauth.callback import (
    GenericRoute,
    PresentCallbackIssuer,
)
from umbod.core.connectors.downstream_mcp.personal.oauth.authorization.models import (
    ClaimPersonalOAuthAttempt,
    CompletePersonalOAuthAttempt,
    PersonalOAuthAttemptQuery,
    PreparedPersonalOAuth,
    PreparePersonalOAuth,
    PublishPersonalOAuthAttempt,
    ReservePersonalOAuthAttempt,
)
from umbod.core.connectors.downstream_mcp.personal.oauth.authorization.ports import (
    PersonalOAuthAttemptStore,
)
from umbod.core.connectors.downstream_mcp.stores import (
    DownstreamMcpStores,
    SaveConnectorDefinition,
    create_downstream_mcp_stores,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_attempts import (
    EncryptedPersonalOAuthAttemptStore,
)
from umbod.core.permissions.stores.schema import (
    CONNECTOR_PERMISSION_TABLE,
    GroupConnectorPermissionKey,
    GroupConnectorPermissionRecord,
)
from umbod.core.persistence import (
    Database,
    TransactionMode,
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


async def initialized_attempt_case(database: Database) -> AttemptCase:
    bundle = await create_downstream_mcp_stores("test-secret", database)
    definition = OAuthConnectorDefinition(
        connector_id="personal",
        display_name="Personal",
        endpoint_url="https://personal.example/mcp",
        authorization_mode="personal",
    )
    await bundle.definitions.save(SaveConnectorDefinition(definition=definition))
    await bundle.publishing.publish_connector(definition.connector_id)
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
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
        database=database,
        clock=clock,
        bundle=bundle,
        store=EncryptedPersonalOAuthAttemptStore(
            database, AuthenticatedTextCipher("test-secret"), clock
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
        route=GenericRoute(kind="generic"),
        issuer=PresentCallbackIssuer(kind="present", value="https://issuer.example"),
        state=case.command.preparation.state,
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
