from umbod.core.configuration.persistence import TextCipher
from umbod.core.persistence import Database, Equals, TransactionMode

from ..models import uses_personal_oauth
from ..personal_connections.authorization_models import ExpiringPersonalToken, PresentPersonalRefreshToken
from ..personal_connections.health_models import RefreshingAuthorization
from .personal_refresh_records import matching_refresh
from ..personal_connections.grant_binding import validated_bound_grant
from ..personal_connections.health_models import (
    ExpiredAuthorization,
    LocallyAuthorized,
    NotAuthorized,
    PersonalAuthorizationHealth,
    PersonalAuthorizationHealthQuery,
    PersonalAuthorizationHealthUnavailable,
    ReconnectRequired,
    UnsupportedAuthorization,
)
from ..personal_connections.models import Authorized, PersonalConnection
from .personal_authorization_rejection_records import matching_rejection
from .personal_connection_records import load_personal_connection
from .personal_oauth_configurations import load_personal_oauth_configuration
from .ports import CONNECTOR_DEFINITION_ADAPTER
from .queries import query_all
from .schema import CONNECTOR_DEFINITION_CONNECTOR_ID, CONNECTOR_DEFINITION_TABLE


class EncryptedPersonalAuthorizationHealthStore:
    def __init__(self, database: Database, cipher: TextCipher) -> None:
        self._database = database
        self._cipher = cipher

    async def get(self, query: PersonalAuthorizationHealthQuery) -> PersonalAuthorizationHealth:
        try:
            async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
                connection = await load_personal_connection(session, self._cipher, query.key)
                if not isinstance(connection, PersonalConnection) or not isinstance(connection.authorization, Authorized):
                    return NotAuthorized()
                row = await session.find_one(CONNECTOR_DEFINITION_TABLE, query_all(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, query.key.connector_id)))
                if row is None:
                    return UnsupportedAuthorization()
                definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(row.document)
                if definition.connector_id != query.key.connector_id or not uses_personal_oauth(definition):
                    return UnsupportedAuthorization()
                configuration = await load_personal_oauth_configuration(session, self._cipher, query.key.connector_id)
                try:
                    grant = validated_bound_grant(connection.authorization, query.key, query.now, definition, configuration.policy)
                except ValueError:
                    return UnsupportedAuthorization()
                if await matching_rejection(session, self._cipher, connection):
                    return ReconnectRequired()
                refresh = await matching_refresh(session, self._cipher, connection, query.now)
                if refresh is not None:
                    if refresh.status in ("refresh_uncertain", "refresh_denied"):
                        return ReconnectRequired(reason=refresh.status)
                    if refresh.deadline <= query.now:
                        return ReconnectRequired(reason="refresh_uncertain")
                    return RefreshingAuthorization(deadline=refresh.deadline)
                refresh_supported = grant.client_mode != "dynamic_public" and isinstance(grant.refresh_token, PresentPersonalRefreshToken)
                if not isinstance(grant.lifetime, ExpiringPersonalToken):
                    return UnsupportedAuthorization()
                if grant.lifetime.expires_at <= query.now:
                    return ExpiredAuthorization(expires_at=grant.lifetime.expires_at, refresh_supported=refresh_supported)
                return LocallyAuthorized(expires_at=grant.lifetime.expires_at, refresh_supported=refresh_supported)
        except Exception:
            pass
        raise PersonalAuthorizationHealthUnavailable("Personal authorization health unavailable")
