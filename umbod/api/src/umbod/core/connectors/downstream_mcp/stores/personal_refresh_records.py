import hashlib
import json
from datetime import datetime

from pydantic import SecretStr

from umbod.core.configuration.persistence import TextCipher
from umbod.core.persistence import AllOf, DatabaseSession, DeleteQuery, Equals, UpsertCommand

from ..personal_connections.models import Authorized, PersonalConnection, PersonalConnectionKey
from ..personal_connections.refresh_models import PersonalRefreshClaim
from .personal_refresh_schema import PERSONAL_REFRESH_NAMESPACE, PERSONAL_REFRESH_SUBJECT, PERSONAL_REFRESH_CONNECTOR_ID, PERSONAL_REFRESH_TABLE
from .queries import query_all
from .schema import PersonalConnectionRecord, PersonalConnectionRecordKey


def refresh_filter(key: PersonalConnectionKey) -> AllOf:
    return AllOf((Equals(PERSONAL_REFRESH_NAMESPACE, key.principal.namespace), Equals(PERSONAL_REFRESH_SUBJECT, key.principal.subject), Equals(PERSONAL_REFRESH_CONNECTOR_ID, key.connector_id)))


async def load_refresh(session: DatabaseSession, cipher: TextCipher, key: PersonalConnectionKey) -> PersonalRefreshClaim | None:
    row = await session.find_one(PERSONAL_REFRESH_TABLE, query_all(refresh_filter(key)))
    if row is None:
        return None
    claim = PersonalRefreshClaim.model_validate_json(cipher.decrypt(row.document))
    if claim.key != key or (row.namespace, row.subject, row.connector_id) != (key.principal.namespace, key.principal.subject, key.connector_id) or claim.grant.key != key:
        raise ValueError("Invalid refresh ownership")
    return claim


async def clear_refresh(session: DatabaseSession, key: PersonalConnectionKey) -> None:
    await session.delete(PERSONAL_REFRESH_TABLE, DeleteQuery(refresh_filter(key)))


def serialize_refresh(value: object) -> str:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("Invalid refresh document")


async def save_refresh(session: DatabaseSession, cipher: TextCipher, claim: PersonalRefreshClaim) -> None:
    key = PersonalConnectionRecordKey(namespace=claim.key.principal.namespace, subject=claim.key.principal.subject, connector_id=claim.key.connector_id)
    await session.upsert(PERSONAL_REFRESH_TABLE, UpsertCommand(key=key, row=PersonalConnectionRecord(**key.model_dump(), document=cipher.encrypt(json.dumps(claim.model_dump(mode="python"), default=serialize_refresh)))))


async def matching_refresh(session: DatabaseSession, cipher: TextCipher, connection: PersonalConnection, now: datetime) -> PersonalRefreshClaim | None:
    claim = await load_refresh(session, cipher, connection.key)
    if claim is None or not isinstance(connection.authorization, Authorized) or claim.credential_fingerprint != hashlib.sha256(connection.authorization.authorization.get_secret_value().encode()).hexdigest():
        return None
    if claim.status == "preparing" and claim.deadline <= now:
        return None
    return claim
