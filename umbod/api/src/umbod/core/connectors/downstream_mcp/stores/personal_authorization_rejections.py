import hashlib

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.configuration.persistence import TextCipher
from umbod.core.persistence import AllOf, Database, DatabaseSession, DeleteQuery, Equals, TransactionMode, UpsertCommand

from ..models import uses_personal_oauth
from ..personal_connections.health_models import PersonalAuthorizationHealthUnavailable, RejectPersonalAuthorization
from ..personal_connections.models import Authorized, PersonalConnection, PersonalConnectionKey
from .personal_connections import load_personal_connection
from .personal_authorization_health_schema import (
    PERSONAL_AUTHORIZATION_REJECTION_CONNECTOR_ID,
    PERSONAL_AUTHORIZATION_REJECTION_NAMESPACE,
    PERSONAL_AUTHORIZATION_REJECTION_SUBJECT,
    PERSONAL_AUTHORIZATION_REJECTION_TABLE,
)
from .ports import CONNECTOR_DEFINITION_ADAPTER
from .queries import query_all
from .schema import CONNECTOR_DEFINITION_CONNECTOR_ID, CONNECTOR_DEFINITION_TABLE, PersonalConnectionRecord, PersonalConnectionRecordKey


class AuthorizationRejection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: PersonalConnectionKey
    credential_fingerprint: str = Field(pattern="^[0-9a-f]{64}$")


def rejection_filter(key: PersonalConnectionKey) -> AllOf:
    return AllOf((
        Equals(PERSONAL_AUTHORIZATION_REJECTION_NAMESPACE, key.principal.namespace),
        Equals(PERSONAL_AUTHORIZATION_REJECTION_SUBJECT, key.principal.subject),
        Equals(PERSONAL_AUTHORIZATION_REJECTION_CONNECTOR_ID, key.connector_id),
    ))


def authorization_fingerprint(authorization: Authorized) -> str:
    return hashlib.sha256(authorization.authorization.get_secret_value().encode()).hexdigest()


async def matching_rejection(session: DatabaseSession, cipher: TextCipher, connection: PersonalConnection) -> bool:
    row = await session.find_one(PERSONAL_AUTHORIZATION_REJECTION_TABLE, query_all(rejection_filter(connection.key)))
    if row is None:
        return False
    rejection = AuthorizationRejection.model_validate_json(cipher.decrypt(row.document))
    if rejection.key != connection.key or (row.namespace, row.subject, row.connector_id) != (connection.key.principal.namespace, connection.key.principal.subject, connection.key.connector_id):
        raise ValueError("Invalid rejection ownership")
    return isinstance(connection.authorization, Authorized) and rejection.credential_fingerprint == authorization_fingerprint(connection.authorization)


async def clear_rejection(session: DatabaseSession, key: PersonalConnectionKey) -> None:
    await session.delete(PERSONAL_AUTHORIZATION_REJECTION_TABLE, DeleteQuery(rejection_filter(key)))


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
            rejection = AuthorizationRejection(key=command.key, credential_fingerprint=authorization_fingerprint(connection.authorization))
            key = PersonalConnectionRecordKey(namespace=command.key.principal.namespace, subject=command.key.principal.subject, connector_id=command.key.connector_id)
            await session.upsert(PERSONAL_AUTHORIZATION_REJECTION_TABLE, UpsertCommand(key=key, row=PersonalConnectionRecord(**key.model_dump(), document=cipher.encrypt(rejection.model_dump_json()))))
    except Exception:
        pass
    else:
        return
    raise PersonalAuthorizationHealthUnavailable("Personal authorization health unavailable")
