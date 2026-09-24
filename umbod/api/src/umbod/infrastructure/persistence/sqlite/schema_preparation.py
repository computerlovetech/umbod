import asyncio

from umbod.infrastructure.persistence.schema_preparation import APPLICATION_PERSISTENCE_TABLES
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase


_SCHEMA_PREPARATION_LOCK = asyncio.Lock()
_SQLITE_SPECIFIC_TABLE_NAMES = frozenset(
    {
        "connector_capability_description_overrides",
        "messaging_checkpoints",
        "messaging_events",
    }
)
_CURRENT_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS connector_capability_description_overrides (
        connector_id TEXT PRIMARY KEY NOT NULL,
        connector_kind TEXT NOT NULL CHECK (connector_kind IN ('native', 'downstream_mcp', 'openapi')),
        state TEXT NOT NULL CHECK (state IN ('system', 'overridden')),
        description TEXT,
        revision INTEGER NOT NULL CHECK (revision > 0),
        CHECK ((state = 'system' AND description IS NULL) OR (state = 'overridden' AND description IS NOT NULL AND length(trim(description)) BETWEEN 1 AND 300))
    )""",
    "CREATE TABLE IF NOT EXISTS messaging_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, document TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS messaging_checkpoints (consumer_id TEXT PRIMARY KEY, sequence INTEGER NOT NULL CHECK(sequence >= 0))",
    "CREATE UNIQUE INDEX IF NOT EXISTS downstream_mcp_connector_definitions_public_path_uq ON downstream_mcp_connector_definitions(public_path)",
    "CREATE INDEX IF NOT EXISTS messaging_events_type_sequence_idx ON messaging_events(event_type, sequence)",
)


class SQLiteCurrentSchemaPreparation:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def execute(self) -> None:
        async with _SCHEMA_PREPARATION_LOCK:
            generic_tables = tuple(
                table
                for table in APPLICATION_PERSISTENCE_TABLES
                if table.name not in _SQLITE_SPECIFIC_TABLE_NAMES
            )
            await self._database.ensure_schema(generic_tables)
            async with self._database.schema_connection() as connection:
                for statement in _CURRENT_SCHEMA_STATEMENTS:
                    await connection.execute(statement)
