import hashlib

from pydantic import BaseModel, ConfigDict, Field

from umbod.core.configuration.persistence import TextCipher
from umbod.core.persistence import AllOf, DatabaseSession, DeleteQuery, Equals

from ..personal_connections.models import Authorized, PersonalConnection, PersonalConnectionKey
from .personal_authorization_health_schema import PERSONAL_AUTHORIZATION_REJECTION_CONNECTOR_ID, PERSONAL_AUTHORIZATION_REJECTION_NAMESPACE, PERSONAL_AUTHORIZATION_REJECTION_SUBJECT, PERSONAL_AUTHORIZATION_REJECTION_TABLE
from .queries import query_all


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


