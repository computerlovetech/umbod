from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr

from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import (
    AbsentPersonalRefreshToken,
    ExpiringPersonalToken,
    PersonalOAuthGrant,
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
)
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import (
    PersonalRuntimeAuthorizationStore,
)
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import (
    PersonalOAuthSettings,
    PreconfiguredPublicOAuthClient,
)
from umbod.core.connectors.downstream_mcp.stores import (
    DownstreamMcpStores,
    SaveConnectorDefinition,
    create_downstream_mcp_stores,
)
from umbod.core.connectors.downstream_mcp.stores.personal_oauth_configurations import (
    install_personal_oauth_configuration,
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


async def _create_runtime_case(database: Database) -> RuntimeCase:
    bundle = await create_downstream_mcp_stores("runtime-secret", database)
    definition = OAuthConnectorDefinition(
        connector_id="personal",
        display_name="Personal",
        endpoint_url="https://resource.example/mcp",
        authorization_mode="personal",
    )
    await bundle.definitions.save(SaveConnectorDefinition(definition=definition))
    await bundle.publishing.publish_connector("personal")
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
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
        database=database,
        bundle=bundle,
        store=bundle.personal_runtime_authorizations,
        query=PersonalRuntimeAuthorizationQuery(key=key, group_ids=("team",), now=now),
        grant=grant,
    )
    await install_authorization(case, authorize_personal_grant(grant))
    return case
