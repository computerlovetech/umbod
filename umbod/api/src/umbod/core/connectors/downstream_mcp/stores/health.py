from pydantic import TypeAdapter

from umbod.core.connectors.downstream_mcp.models import ConnectorHealth
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorHealthFound,
    ConnectorHealthMissing,
    ConnectorIdQuery,
    SaveConnectorHealth,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_HEALTH_CONNECTOR_ID,
    ConnectorHealthKey,
    ConnectorHealthRecord,
)
from umbod.core.persistence import (
    AllFields,
    Database,
    DeleteQuery,
    Equals,
    Query,
    Table,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


_HEALTH_ADAPTER = TypeAdapter(ConnectorHealth)


class ConnectorHealthStoreService:
    def __init__(
        self,
        database: Database,
        table: Table[ConnectorHealthRecord, ConnectorHealthKey],
    ) -> None:
        self._database = database
        self._table = table

    async def save(self, command: SaveConnectorHealth) -> ConnectorHealthFound:
        record = ConnectorHealthRecord(
            connector_id=command.health.connector_id,
            document=command.health.model_dump(mode="json"),
        )
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            await session.upsert(
                self._table,
                UpsertCommand(
                    key=ConnectorHealthKey(connector_id=command.health.connector_id),
                    row=record,
                ),
            )
        return ConnectorHealthFound(health=command.health)

    async def get(self, query: ConnectorIdQuery) -> ConnectorHealthFound | ConnectorHealthMissing:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            row = await session.find_one(
                self._table,
                Query(
                    filter=Equals(CONNECTOR_HEALTH_CONNECTOR_ID, query.connector_id),
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )
        if row is None:
            return ConnectorHealthMissing(connector_id=query.connector_id)
        return ConnectorHealthFound(health=_HEALTH_ADAPTER.validate_python(row.document))

    async def delete(
        self, command: ConnectorIdQuery
    ) -> ConnectorHealthFound | ConnectorHealthMissing:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            row = await session.find_one(
                self._table,
                Query(
                    filter=Equals(CONNECTOR_HEALTH_CONNECTOR_ID, command.connector_id),
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )
            if row is not None:
                await session.delete(
                    self._table,
                    DeleteQuery(Equals(CONNECTOR_HEALTH_CONNECTOR_ID, command.connector_id)),
                )
        if row is None:
            return ConnectorHealthMissing(connector_id=command.connector_id)
        return ConnectorHealthFound(health=_HEALTH_ADAPTER.validate_python(row.document))
