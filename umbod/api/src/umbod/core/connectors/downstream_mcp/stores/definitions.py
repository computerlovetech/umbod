from pydantic import TypeAdapter

from umbod.core.connectors.downstream_mcp.models import ConnectorDefinition
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionFound,
    ConnectorDefinitionList,
    ConnectorDefinitionMissing,
    ConnectorIdQuery,
    PublicPathQuery,
    SaveConnectorDefinition,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    CONNECTOR_DEFINITION_CONNECTOR_ID,
    CONNECTOR_DEFINITION_PUBLIC_PATH,
    ConnectorDefinitionKey,
    ConnectorDefinitionRecord,
)
from umbod.core.persistence import (
    AllFields,
    Database,
    DeleteQuery,
    Equals,
    NoFilter,
    OrderBy,
    Query,
    Table,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


_DEFINITION_ADAPTER = TypeAdapter(ConnectorDefinition)


class ConnectorDefinitionStoreService:
    def __init__(
        self,
        database: Database,
        table: Table[ConnectorDefinitionRecord, ConnectorDefinitionKey],
    ) -> None:
        self._database = database
        self._table = table

    async def save(self, command: SaveConnectorDefinition) -> ConnectorDefinitionFound:
        definition = _DEFINITION_ADAPTER.validate_python(command.definition)
        record = ConnectorDefinitionRecord(
            connector_id=definition.connector_id,
            document=definition.model_dump(mode="json"),
            public_path=definition.public_path,
            capability_description=definition.capability_description,
        )
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            existing = await session.find_one(
                self._table,
                Query(
                    filter=Equals(CONNECTOR_DEFINITION_PUBLIC_PATH, definition.public_path),
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )
            if existing is not None and existing.connector_id != definition.connector_id:
                raise ValueError("public path already exists")
            await session.upsert(
                self._table,
                UpsertCommand(
                    key=ConnectorDefinitionKey(connector_id=definition.connector_id),
                    row=record,
                ),
            )
        return ConnectorDefinitionFound(definition=definition)

    async def get(
        self, query: ConnectorIdQuery
    ) -> ConnectorDefinitionFound | ConnectorDefinitionMissing:
        row = await self._find(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, query.connector_id))
        if row is None:
            return ConnectorDefinitionMissing(connector_id=query.connector_id)
        return ConnectorDefinitionFound(definition=_decode_definition(row))

    async def list(self) -> ConnectorDefinitionList:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            rows = await session.find_many(
                self._table,
                Query(
                    filter=NoFilter(),
                    projection=AllFields(),
                    ordering=OrderBy((CONNECTOR_DEFINITION_CONNECTOR_ID,)),
                ),
            )
        return ConnectorDefinitionList(definitions=tuple(_decode_definition(row) for row in rows))

    async def get_by_public_path(
        self, query: PublicPathQuery
    ) -> ConnectorDefinitionFound | ConnectorDefinitionMissing:
        row = await self._find(Equals(CONNECTOR_DEFINITION_PUBLIC_PATH, query.public_path))
        if row is None:
            return ConnectorDefinitionMissing(connector_id=query.public_path)
        return ConnectorDefinitionFound(definition=_decode_definition(row))

    async def delete(
        self, command: ConnectorIdQuery
    ) -> ConnectorDefinitionFound | ConnectorDefinitionMissing:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            row = await session.find_one(
                self._table,
                Query(
                    filter=Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, command.connector_id),
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )
            if row is not None:
                await session.delete(
                    self._table,
                    DeleteQuery(Equals(CONNECTOR_DEFINITION_CONNECTOR_ID, command.connector_id)),
                )
        if row is None:
            return ConnectorDefinitionMissing(connector_id=command.connector_id)
        return ConnectorDefinitionFound(definition=_decode_definition(row))

    async def _find(
        self, predicate: Equals[ConnectorDefinitionRecord, str]
    ) -> ConnectorDefinitionRecord | None:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            return await session.find_one(
                self._table,
                Query(
                    filter=predicate,
                    projection=AllFields(),
                    ordering=Unordered(),
                ),
            )


def _decode_definition(record: ConnectorDefinitionRecord) -> ConnectorDefinition:
    return _DEFINITION_ADAPTER.validate_python(record.document)
