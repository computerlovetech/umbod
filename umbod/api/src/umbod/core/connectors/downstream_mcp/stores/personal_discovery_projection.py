from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, TypeAdapter

from umbod.core.configuration.persistence import TextCipher
from umbod.core.configuration.exceptions import ConnectorConfigurationDecryptionError
from umbod.core.persistence import AllOf, DatabaseSession, Equals, UpsertCommand

from ..models import DomainModel, uses_personal_oauth
from ..personal_connections.models import Authorized, PersonalConnection, PersonalConnectionKey
from ..personal_connections.authorization_models import PersonalOAuthGrant, ExpiringPersonalToken
from ..personal_connections.grant_binding import validated_bound_grant
from .personal_discovery_schema import PERSONAL_DISCOVERY_TABLE, PERSONAL_DISCOVERY_NAMESPACE, PERSONAL_DISCOVERY_SUBJECT, PERSONAL_DISCOVERY_CONNECTOR_ID
from .queries import query_all
from .schema import PersonalConnectionRecord, PersonalConnectionRecordKey, CONNECTOR_DEFINITION_TABLE, CONNECTOR_DEFINITION_CONNECTOR_ID
from .personal_connection_records import load_personal_connection
from .personal_authorization_rejection_records import matching_rejection, authorization_fingerprint
from .personal_oauth_configurations import load_personal_oauth_configuration
from .personal_refresh_records import load_refresh
from .ports import CONNECTOR_DEFINITION_ADAPTER


class AvailableRefresh(DomainModel):
    kind: Literal["available"]


class PreparingRefresh(DomainModel):
    kind: Literal["preparing"]
    deadline: AwareDatetime


class BlockedRefresh(DomainModel):
    kind: Literal["blocked"]


class UnavailableDiscovery(DomainModel):
    kind: Literal["unavailable"]
    key: PersonalConnectionKey


class AvailableDiscovery(DomainModel):
    kind: Literal["available"]
    key: PersonalConnectionKey
    authorization_revision: str = Field(min_length=1)
    configuration_revision: str = Field(min_length=1)
    endpoint_url: str
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    refresh: Annotated[AvailableRefresh | PreparingRefresh | BlockedRefresh, Field(discriminator="kind")]


DiscoveryAvailability = Annotated[UnavailableDiscovery | AvailableDiscovery, Field(discriminator="kind")]
DISCOVERY_AVAILABILITY_ADAPTER = TypeAdapter(DiscoveryAvailability)


def discovery_filter(key: PersonalConnectionKey) -> AllOf:
    return AllOf((Equals(PERSONAL_DISCOVERY_NAMESPACE, key.principal.namespace), Equals(PERSONAL_DISCOVERY_SUBJECT, key.principal.subject), Equals(PERSONAL_DISCOVERY_CONNECTOR_ID, key.connector_id)))


async def _project(session: DatabaseSession, cipher: TextCipher, key: PersonalConnectionKey) -> DiscoveryAvailability:
    connection = await load_personal_connection(session, cipher, key)
    if not isinstance(connection, PersonalConnection) or not connection.enabled or not isinstance(connection.authorization, Authorized):
        return UnavailableDiscovery(kind="unavailable", key=key)
    row = await session.find_one(CONNECTOR_DEFINITION_TABLE, query_all(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, key.connector_id)))
    if row is None:
        return UnavailableDiscovery(kind="unavailable", key=key)
    definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(row.document)
    if definition.connector_id != key.connector_id or not uses_personal_oauth(definition):
        return UnavailableDiscovery(kind="unavailable", key=key)
    configuration = await load_personal_oauth_configuration(session, cipher, key.connector_id)
    parsed = PersonalOAuthGrant.model_validate_json(connection.authorization.authorization.get_secret_value())
    grant = validated_bound_grant(connection.authorization, key, parsed.issued_at, definition, configuration.policy)
    if not isinstance(grant.lifetime, ExpiringPersonalToken) or await matching_rejection(session, cipher, connection):
        return UnavailableDiscovery(kind="unavailable", key=key)
    refresh: AvailableRefresh | PreparingRefresh | BlockedRefresh = AvailableRefresh(kind="available")
    claim = await load_refresh(session, cipher, key)
    if claim is not None and claim.credential_fingerprint == authorization_fingerprint(connection.authorization):
        refresh = PreparingRefresh(kind="preparing", deadline=claim.deadline) if claim.status == "preparing" else BlockedRefresh(kind="blocked")
    return AvailableDiscovery(kind="available", key=key, authorization_revision=connection.revision, configuration_revision=configuration.policy.revision, endpoint_url=definition.endpoint_url, issued_at=grant.issued_at, expires_at=grant.lifetime.expires_at, refresh=refresh)


async def update_personal_discovery(session: DatabaseSession, cipher: TextCipher, key: PersonalConnectionKey) -> None:
    try:
        availability = await _project(session, cipher, key)
    except (ValueError, TypeError, KeyError, ConnectorConfigurationDecryptionError):
        availability = UnavailableDiscovery(kind="unavailable", key=key)
    record_key = PersonalConnectionRecordKey(namespace=key.principal.namespace, subject=key.principal.subject, connector_id=key.connector_id)
    await session.upsert(PERSONAL_DISCOVERY_TABLE, UpsertCommand(key=record_key, row=PersonalConnectionRecord(**record_key.model_dump(), document=cipher.encrypt(availability.model_dump_json()))))
