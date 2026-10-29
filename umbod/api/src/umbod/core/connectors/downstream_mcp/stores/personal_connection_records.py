from umbod.core.configuration.persistence import TextCipher
from umbod.core.persistence import AllFields, AllOf, DatabaseSession, Equals, Query, Unordered

from ..personal_connections.models import MissingPersonalConnection, PersonalConnection, PersonalConnectionKey, PersonalConnectionState
from .schema import PERSONAL_CONNECTION_TABLE, PERSONAL_CONNECTION_NAMESPACE, PERSONAL_CONNECTION_SUBJECT, PERSONAL_CONNECTION_CONNECTOR_ID


async def load_personal_connection(
    session: DatabaseSession, cipher: TextCipher, key: PersonalConnectionKey
) -> PersonalConnectionState:
    row = await session.find_one(
        PERSONAL_CONNECTION_TABLE,
        Query(
            filter=AllOf(
                (
                    Equals(PERSONAL_CONNECTION_NAMESPACE, key.principal.namespace),
                    Equals(PERSONAL_CONNECTION_SUBJECT, key.principal.subject),
                    Equals(PERSONAL_CONNECTION_CONNECTOR_ID, key.connector_id),
                )
            ),
            projection=AllFields(),
            ordering=Unordered(),
        ),
    )
    if row is None:
        return MissingPersonalConnection(key=key)
    state = PersonalConnection.model_validate_json(cipher.decrypt(row.document))
    expected = (key.principal.namespace, key.principal.subject, key.connector_id)
    stored = (row.namespace, row.subject, row.connector_id)
    if stored != expected or state.key != key:
        raise ValueError("Personal connection ownership mismatch")
    return state


