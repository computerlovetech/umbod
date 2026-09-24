from umbod.core.connectors.downstream_mcp.models import (
    CatalogReconciliation,
    DiscoveredTool,
    ToolCatalogSnapshot,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorIdQuery,
    ReplaceToolCatalog,
    ToolCatalogFound,
    ToolCatalogMissing,
)
from umbod.core.connectors.downstream_mcp.stores.schema import (
    TOOL_CATALOG_CONNECTOR_ID,
    ToolCatalogKey,
    ToolCatalogRecord,
)
from umbod.core.persistence import (
    AllFields,
    Database,
    DatabaseSession,
    DeleteQuery,
    Equals,
    Query,
    Table,
    TransactionMode,
    Unordered,
    UpsertCommand,
)


def reconcile_catalogs(
    previous_tools: dict[str, DiscoveredTool], current: ToolCatalogSnapshot
) -> CatalogReconciliation:
    current_tools = {tool.identity.downstream_name: tool for tool in current.tools}
    previous_names = set(previous_tools)
    current_names = set(current_tools)
    shared_names = previous_names & current_names

    def identity(name: str) -> ToolIdentity:
        return ToolIdentity(connector_id=current.connector_id, downstream_name=name)

    return CatalogReconciliation(
        connector_id=current.connector_id,
        added=tuple(identity(name) for name in sorted(current_names - previous_names)),
        changed=tuple(
            identity(name)
            for name in sorted(shared_names)
            if previous_tools[name] != current_tools[name]
        ),
        removed=tuple(identity(name) for name in sorted(previous_names - current_names)),
        unchanged=tuple(
            identity(name)
            for name in sorted(shared_names)
            if previous_tools[name] == current_tools[name]
        ),
    )


async def find_catalog_record(
    session: DatabaseSession,
    table: Table[ToolCatalogRecord, ToolCatalogKey],
    connector_id: str,
) -> ToolCatalogRecord | None:
    return await session.find_one(
        table,
        Query(
            filter=Equals(TOOL_CATALOG_CONNECTOR_ID, connector_id),
            projection=AllFields(),
            ordering=Unordered(),
        ),
    )


async def replace_catalog(
    session: DatabaseSession,
    table: Table[ToolCatalogRecord, ToolCatalogKey],
    command: ReplaceToolCatalog,
) -> CatalogReconciliation:
    snapshot = ToolCatalogSnapshot.model_validate(command.snapshot)
    previous_record = await find_catalog_record(session, table, snapshot.connector_id)
    previous_tools: dict[str, DiscoveredTool] = {}
    if previous_record is not None:
        previous = ToolCatalogSnapshot.model_validate(previous_record.snapshot)
        previous_tools = {tool.identity.downstream_name: tool for tool in previous.tools}
    reconciliation = reconcile_catalogs(previous_tools, snapshot)
    await session.upsert(
        table,
        UpsertCommand(
            key=ToolCatalogKey(connector_id=snapshot.connector_id),
            row=ToolCatalogRecord(
                connector_id=snapshot.connector_id,
                snapshot=snapshot.model_dump(mode="json"),
            ),
        ),
    )
    return reconciliation


class ToolCatalogStoreService:
    def __init__(
        self,
        database: Database,
        table: Table[ToolCatalogRecord, ToolCatalogKey],
    ) -> None:
        self._database = database
        self._table = table

    async def replace(self, command: ReplaceToolCatalog) -> CatalogReconciliation:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            return await replace_catalog(session, self._table, command)

    async def get(self, query: ConnectorIdQuery) -> ToolCatalogFound | ToolCatalogMissing:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            row = await find_catalog_record(session, self._table, query.connector_id)
        if row is None:
            return ToolCatalogMissing(connector_id=query.connector_id)
        return ToolCatalogFound(snapshot=ToolCatalogSnapshot.model_validate(row.snapshot))

    async def delete(self, command: ConnectorIdQuery) -> ToolCatalogFound | ToolCatalogMissing:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            row = await find_catalog_record(session, self._table, command.connector_id)
            await session.delete(
                self._table,
                DeleteQuery(Equals(TOOL_CATALOG_CONNECTOR_ID, command.connector_id)),
            )
        if row is None:
            return ToolCatalogMissing(connector_id=command.connector_id)
        return ToolCatalogFound(snapshot=ToolCatalogSnapshot.model_validate(row.snapshot))
