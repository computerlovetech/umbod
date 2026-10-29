from umbod.core.configuration.persistence import TextCipher
from umbod.core.connectors.downstream_mcp.personal_connections.models import CanonicalPrincipal, PersonalConnectionKey
from umbod.core.connectors.downstream_mcp.stores.personal_discovery_projection import discovery_filter, update_personal_discovery
from umbod.core.connectors.downstream_mcp.stores.personal_discovery_schema import PERSONAL_DISCOVERY_TABLE, PERSONAL_DISCOVERY_NAMESPACE, PERSONAL_DISCOVERY_SUBJECT, PERSONAL_DISCOVERY_CONNECTOR_ID
from umbod.core.connectors.downstream_mcp.stores.schema import PERSONAL_CONNECTION_TABLE, PERSONAL_CONNECTION_NAMESPACE, PERSONAL_CONNECTION_SUBJECT, PERSONAL_CONNECTION_CONNECTOR_ID, PersonalConnectionRecordKey
from umbod.core.persistence import Fields, Database, NoFilter, Query, TransactionMode, Unordered
from umbod.core.connectors.downstream_mcp.stores.queries import query_all


class PersonalDiscoveryPreparation:
    def __init__(self, database: Database, cipher: TextCipher) -> None:
        self._database = database
        self._cipher = cipher

    async def prepare(self) -> None:
        async with self._database.read_session() as session:
            rows = await session.find_many(PERSONAL_CONNECTION_TABLE, Query(filter=NoFilter(), projection=Fields(PersonalConnectionRecordKey, (PERSONAL_CONNECTION_NAMESPACE, PERSONAL_CONNECTION_SUBJECT, PERSONAL_CONNECTION_CONNECTOR_ID)), ordering=Unordered()))
            existing_rows = await session.find_many(PERSONAL_DISCOVERY_TABLE, Query(filter=NoFilter(), projection=Fields(PersonalConnectionRecordKey, (PERSONAL_DISCOVERY_NAMESPACE, PERSONAL_DISCOVERY_SUBJECT, PERSONAL_DISCOVERY_CONNECTOR_ID)), ordering=Unordered()))
            existing_keys = {(row.namespace, row.subject, row.connector_id) for row in existing_rows}
        for row in rows:
            if (row.namespace, row.subject, row.connector_id) in existing_keys:
                continue
            key = PersonalConnectionKey(principal=CanonicalPrincipal(namespace=row.namespace, subject=row.subject), connector_id=row.connector_id)
            async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
                existing = await session.find_one(PERSONAL_DISCOVERY_TABLE, query_all(discovery_filter(key)))
                if existing is None:
                    await update_personal_discovery(session, self._cipher, key)
