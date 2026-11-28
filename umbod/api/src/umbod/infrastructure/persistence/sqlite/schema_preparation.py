import asyncio
from uuid import uuid4

from aiosqlite import Connection

from umbod.core.filesystem.stores.namespaces import adopt_existing_homes
from umbod.core.groups.stores.schema import GROUP_TABLE
from umbod.infrastructure.persistence.group_reconciliation import reconcile_group_catalogue
from umbod.infrastructure.persistence.schema_preparation import APPLICATION_PERSISTENCE_TABLES
from umbod.infrastructure.persistence.sqlite.compiler import SQLiteCompiler
from umbod.infrastructure.persistence.sqlite.database import SQLiteDatabase
from umbod.infrastructure.persistence.sqlite.value_mapping import SQLiteValueMapper


_SCHEMA_PREPARATION_LOCK = asyncio.Lock()
_SQLITE_SPECIFIC_TABLE_NAMES = frozenset(
    {
        "connector_capability_description_overrides",
        "messaging_checkpoints",
    }
)
_CURRENT_SCHEMA_STATEMENTS = (
    "CREATE UNIQUE INDEX IF NOT EXISTS filesystem_namespaces_root_uq ON filesystem_namespaces(root_node_id)",
    "CREATE INDEX IF NOT EXISTS personal_usage_events_day_idx ON personal_usage_events(day)",
    "CREATE INDEX IF NOT EXISTS personal_usage_events_owner_day_idx ON personal_usage_events(owner_id, day)",
    "CREATE INDEX IF NOT EXISTS personal_usage_daily_day_idx ON personal_usage_daily(day)",
    "CREATE INDEX IF NOT EXISTS personal_usage_tool_daily_day_idx ON personal_usage_tool_daily(day)",
    """CREATE TABLE IF NOT EXISTS connector_capability_description_overrides (
        connector_id TEXT PRIMARY KEY NOT NULL,
        connector_kind TEXT NOT NULL CHECK (connector_kind IN ('native', 'downstream_mcp', 'openapi')),
        state TEXT NOT NULL CHECK (state IN ('system', 'overridden')),
        description TEXT,
        revision INTEGER NOT NULL CHECK (revision > 0),
        CHECK ((state = 'system' AND description IS NULL) OR (state = 'overridden' AND description IS NOT NULL AND length(trim(description)) BETWEEN 1 AND 300))
    )""",
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
                await _prepare_group_catalogue(connection)
            await reconcile_group_catalogue(self._database)
            await adopt_existing_homes(self._database)


async def _prepare_group_catalogue(connection: Connection) -> None:
    async with connection.execute("PRAGMA table_info(mcp_permission_groups)") as cursor:
        columns = {row["name"] for row in await cursor.fetchall()}
    if "label" not in columns:
        await connection.execute(
            "ALTER TABLE mcp_permission_groups ADD COLUMN label TEXT NOT NULL DEFAULT ''"
        )
        await connection.execute("UPDATE mcp_permission_groups SET label = group_id")
    if "description" not in columns:
        await connection.execute(
            "ALTER TABLE mcp_permission_groups ADD COLUMN description TEXT NOT NULL DEFAULT ''"
        )
    if "revision" not in columns:
        await connection.execute(
            "ALTER TABLE mcp_permission_groups ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0)"
        )
    if "instance_id" not in columns:
        await _backfill_group_instances(connection)
    await connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS mcp_permission_groups_instance_id_uq "
        "ON mcp_permission_groups(instance_id)"
    )
    await connection.execute(
        "INSERT OR IGNORE INTO mcp_permission_group_instance_reservations (instance_id) "
        "SELECT instance_id FROM mcp_permission_groups"
    )


async def _backfill_group_instances(connection: Connection) -> None:
    await connection.execute(
        "ALTER TABLE mcp_permission_groups RENAME TO mcp_permission_groups_legacy"
    )
    create_groups = SQLiteCompiler(SQLiteValueMapper()).create_table(GROUP_TABLE)
    await connection.execute(create_groups.statement, create_groups.parameters)
    async with connection.execute(
        "SELECT group_id, label, description, revision FROM mcp_permission_groups_legacy"
    ) as cursor:
        rows = await cursor.fetchall()
    await connection.executemany(
        "INSERT INTO mcp_permission_groups (group_id, label, description, revision, instance_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ((*row, uuid4().hex) for row in rows),
    )
    await connection.execute("DROP TABLE mcp_permission_groups_legacy")
