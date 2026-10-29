from umbod.core.configuration.persistence import TextCipher
from umbod.core.permissions.stores.schema import (
    CONNECTOR_PERMISSION_CONNECTOR_ID,
    CONNECTOR_PERMISSION_GROUP_ID,
    CONNECTOR_PERMISSION_TABLE,
)
from umbod.core.persistence import (
    AllOf,
    Database,
    DatabaseSession,
    Equals,
    OneOf,
    TransactionMode,
)
from umbod.core.publishing.stores.schema import (
    PUBLICATION_STATE_CONNECTOR_ID,
    PUBLICATION_STATE_TABLE,
)

from ..models import uses_personal_oauth
from ..personal_connections.authorization_models import (
    ExpiringPersonalToken,
)
from ..personal_connections.models import Authorized, PersonalConnection
from ..personal_connections.runtime_models import (
    PersonalRuntimeAuthorizationQuery,
    PersonalRuntimeTarget,
    PersonalRuntimeUnavailable,
)
from ..personal_connections.grant_binding import validated_bound_grant
from ..personal_connections.health_models import RejectPersonalAuthorization
from .personal_authorization_rejection_records import matching_rejection
from .personal_authorization_rejections import record_rejection
from .personal_connection_records import load_personal_connection
from .personal_refresh_records import matching_refresh
from .personal_oauth_configurations import load_personal_oauth_configuration
from .ports import CONNECTOR_DEFINITION_ADAPTER
from .schema import CONNECTOR_DEFINITION_CONNECTOR_ID, CONNECTOR_DEFINITION_TABLE

from .queries import query_all as _query


async def load_personal_runtime_target(
    session: DatabaseSession,
    cipher: TextCipher,
    query: PersonalRuntimeAuthorizationQuery,
) -> PersonalRuntimeTarget:
    try:
        return await _load_target(session, cipher, query)
    except PersonalRuntimeUnavailable:
        raise
    except Exception:
        raise PersonalRuntimeUnavailable(
            "Personal authorization requires reconnect"
        ) from None


async def _load_target(
    session: DatabaseSession,
    cipher: TextCipher,
    query: PersonalRuntimeAuthorizationQuery,
) -> PersonalRuntimeTarget:
    connector_id = query.key.connector_id
    definition_row = await session.find_one(
        CONNECTOR_DEFINITION_TABLE,
        _query(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, connector_id)),
    )
    if definition_row is None:
        raise PersonalRuntimeUnavailable("Personal connector unavailable")
    definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(definition_row.document)
    if definition.connector_id != connector_id or not uses_personal_oauth(definition):
        raise PersonalRuntimeUnavailable("Personal connector unavailable")
    configuration = await load_personal_oauth_configuration(
        session, cipher, connector_id
    )
    connection = await load_personal_connection(session, cipher, query.key)
    if (
        not isinstance(connection, PersonalConnection)
        or not connection.enabled
        or not isinstance(connection.authorization, Authorized)
    ):
        raise PersonalRuntimeUnavailable("Personal authorization unavailable")
    publication = await session.find_one(
        PUBLICATION_STATE_TABLE,
        _query(Equals(PUBLICATION_STATE_CONNECTOR_ID, connector_id)),
    )
    if publication is None or not publication.published or not query.group_ids:
        raise PersonalRuntimeUnavailable("Personal connector unavailable")
    permission = await session.find_one(
        CONNECTOR_PERMISSION_TABLE,
        _query(
            AllOf(
                (
                    Equals(CONNECTOR_PERMISSION_CONNECTOR_ID, connector_id),
                    OneOf(CONNECTOR_PERMISSION_GROUP_ID, query.group_ids),
                )
            )
        ),
    )
    if permission is None:
        raise PersonalRuntimeUnavailable("Personal connector unavailable")
    grant = validated_bound_grant(connection.authorization, query.key, query.now, definition, configuration.policy)
    policy = configuration.policy
    if await matching_refresh(session, cipher, connection, query.now):
        raise PersonalRuntimeUnavailable("Personal authorization recovery in progress")
    if await matching_rejection(session, cipher, connection):
        raise PersonalRuntimeUnavailable("Personal authorization requires reconnect")
    if not isinstance(grant.lifetime, ExpiringPersonalToken):
        raise PersonalRuntimeUnavailable("Personal authorization has unsupported lifetime")
    if grant.lifetime.expires_at <= query.now:
        raise PersonalRuntimeUnavailable("Personal authorization expired")
    return PersonalRuntimeTarget(
        key=query.key,
        authorization_revision=connection.revision,
        configuration_revision=policy.revision,
        endpoint_url=definition.endpoint_url,
        access_token=grant.access_token,
        expires_at=grant.lifetime.expires_at,
    )


class EncryptedPersonalRuntimeAuthorizationStore:
    def __init__(self, database: Database, cipher: TextCipher) -> None:
        self._database = database
        self._cipher = cipher

    async def reject_authorization(self, command: RejectPersonalAuthorization) -> None:
        await record_rejection(self._database, self._cipher, command)

    async def resolve(
        self, query: PersonalRuntimeAuthorizationQuery
    ) -> PersonalRuntimeTarget:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            return await load_personal_runtime_target(session, self._cipher, query)
