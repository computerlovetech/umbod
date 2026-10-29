from .personal_discovery_projection import update_personal_discovery

from . import personal_authorization_rejection_records as rejection_records

from umbod.core.configuration.persistence import TextCipher
from umbod.core.messaging.discovery_events import connector_discovery_changed_event
from umbod.core.messaging.stores.event_stream import append_event_in_session
from umbod.core.persistence import Database, Equals, TransactionMode, UpsertCommand

from ..models import uses_personal_oauth
from ..personal_connections.health_models import PersonalAuthorizationHealthUnavailable, RejectPersonalAuthorization
from ..personal_connections.models import Authorized, PersonalConnection
from .personal_connection_records import load_personal_connection
from .personal_authorization_health_schema import (
    PERSONAL_AUTHORIZATION_REJECTION_TABLE,
)
from .ports import CONNECTOR_DEFINITION_ADAPTER
from .queries import query_all
from .schema import CONNECTOR_DEFINITION_CONNECTOR_ID, CONNECTOR_DEFINITION_TABLE, PersonalConnectionRecord, PersonalConnectionRecordKey


async def record_rejection(database: Database, cipher: TextCipher, command: RejectPersonalAuthorization) -> None:
    try:
        async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            row = await session.find_one(CONNECTOR_DEFINITION_TABLE, query_all(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, command.key.connector_id)))
            if row is None:
                return
            definition = CONNECTOR_DEFINITION_ADAPTER.validate_python(row.document)
            if definition.connector_id != command.key.connector_id or not uses_personal_oauth(definition):
                return
            connection = await load_personal_connection(session, cipher, command.key)
            if not isinstance(connection, PersonalConnection) or not isinstance(connection.authorization, Authorized) or connection.revision != command.expected_connection_revision:
                return
            if await rejection_records.matching_rejection(session, cipher, connection):
                return
            rejection = rejection_records.AuthorizationRejection(key=command.key, credential_fingerprint=rejection_records.authorization_fingerprint(connection.authorization))
            key = PersonalConnectionRecordKey(namespace=command.key.principal.namespace, subject=command.key.principal.subject, connector_id=command.key.connector_id)
            await session.upsert(PERSONAL_AUTHORIZATION_REJECTION_TABLE, UpsertCommand(key=key, row=PersonalConnectionRecord(**key.model_dump(), document=cipher.encrypt(rejection.model_dump_json()))))
            await update_personal_discovery(session, cipher, command.key)
            await append_event_in_session(session, connector_discovery_changed_event("downstream_mcp", command.key.connector_id))
    except Exception:
        pass
    else:
        return
    raise PersonalAuthorizationHealthUnavailable("Personal authorization health unavailable")
