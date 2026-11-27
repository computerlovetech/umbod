import aiosqlite

from umbod.core.telemetry.analytics import LogDimension
from umbod.core.telemetry.analytics.activity import classify_activity

APPLICATION_ID = 1431126350
SCHEMA_VERSION = 4
LEGACY_COLUMNS = (
    ("occurred_at_us", "INTEGER", 1),
    ("owner_id", "TEXT", 0),
    ("source", "TEXT", 0),
    ("event_name", "TEXT", 0),
    ("severity", "TEXT", 0),
    ("session_id", "TEXT", 0),
    ("tool_name", "TEXT", 0),
)
ACTIVITY_COLUMNS = LEGACY_COLUMNS + (("activity_kind", "TEXT", 0), ("outcome", "TEXT", 0))
NORMALIZATION_COLUMNS = ACTIVITY_COLUMNS + (("normalization_json", "TEXT", 0),)
COLUMNS = NORMALIZATION_COLUMNS + (("raw_batch_id", "INTEGER", 0), ("raw_record_index", "INTEGER", 0))
RAW_BATCH_COLUMNS = (
    ("id", "INTEGER", 1),
    ("raw_payload", "BLOB", 1),
    ("encoding", "TEXT", 1),
    ("received_at_us", "INTEGER", 1),
    ("owner_id", "TEXT", 0),
)


async def _schema_identity(connection: aiosqlite.Connection) -> tuple[int, int]:
    async with connection.execute("PRAGMA application_id") as cursor:
        application_id = (await cursor.fetchone())[0]
    async with connection.execute("PRAGMA user_version") as cursor:
        version = (await cursor.fetchone())[0]
    return application_id, version


async def ensure_schema(connection: aiosqlite.Connection) -> None:
    application_id, version = await _schema_identity(connection)
    async with connection.execute(
        "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
    ) as cursor:
        objects = await cursor.fetchall()
    if application_id == 0 and version == 0 and not objects:
        await connection.execute(
            "CREATE TABLE analytics_logs (occurred_at_us INTEGER NOT NULL, "
            "owner_id TEXT, source TEXT, event_name TEXT, severity TEXT, "
            "session_id TEXT, tool_name TEXT, activity_kind TEXT, outcome TEXT, "
            "normalization_json TEXT)"
        )
        await connection.execute(
            "CREATE INDEX analytics_logs_time_owner "
            "ON analytics_logs (occurred_at_us, owner_id)"
        )
        await connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        version = 3
    elif application_id != APPLICATION_ID or version not in (1, 2, 3, SCHEMA_VERSION):
        raise ValueError("Unrecognized analytics database")
    if version == 1:
        await _validate_columns(connection, "analytics_logs", LEGACY_COLUMNS)
        await _migrate_activity(connection)
        version = 2
    if version == 2:
        await _validate_columns(connection, "analytics_logs", ACTIVITY_COLUMNS)
        await connection.execute("ALTER TABLE analytics_logs ADD COLUMN normalization_json TEXT")
        version = 3
    if version == 3:
        await _validate_columns(connection, "analytics_logs", NORMALIZATION_COLUMNS)
        await _migrate_raw_archive(connection)
        await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    await validate_current_schema(connection)
    await connection.execute(
        "CREATE INDEX IF NOT EXISTS analytics_logs_owner_session "
        "ON analytics_logs (owner_id, source, session_id)"
    )


async def validate_current_schema(connection: aiosqlite.Connection) -> None:
    if await _schema_identity(connection) != (APPLICATION_ID, SCHEMA_VERSION):
        raise ValueError("Unrecognized analytics database")
    await _validate_columns(connection, "analytics_logs", COLUMNS)
    await _validate_archive_schema(connection)


async def _validate_columns(
    connection: aiosqlite.Connection, table: str, expected: tuple[tuple[str, str, int], ...],
) -> None:
    async with connection.execute(
        'SELECT name, type, "notnull" FROM pragma_table_info(?) ORDER BY cid', (table,),
    ) as cursor:
        columns = tuple(tuple(row) for row in await cursor.fetchall())
    if columns != expected:
        raise ValueError("Invalid analytics schema")


async def _validate_archive_schema(connection: aiosqlite.Connection) -> None:
    await _validate_columns(connection, "analytics_raw_batches", RAW_BATCH_COLUMNS)
    async with connection.execute(
        "SELECT name FROM pragma_table_info('analytics_raw_batches') WHERE pk > 0"
    ) as cursor:
        if [row[0] for row in await cursor.fetchall()] != ["id"]:
            raise ValueError("Invalid analytics schema")
    async with connection.execute(
        'SELECT info.name FROM pragma_index_list(\'analytics_logs\') AS indexes '
        'JOIN pragma_index_info(indexes.name) AS info '
        'WHERE indexes.name = \'analytics_logs_raw_record\' AND indexes."unique" = 1 '
        'AND indexes.partial = 0 ORDER BY info.seqno'
    ) as cursor:
        if [row[0] for row in await cursor.fetchall()] != ["raw_batch_id", "raw_record_index"]:
            raise ValueError("Invalid analytics schema")


async def _migrate_raw_archive(connection: aiosqlite.Connection) -> None:
    await connection.execute(
        "CREATE TABLE analytics_raw_batches ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "
        "raw_payload BLOB NOT NULL CHECK(typeof(raw_payload) = 'blob' AND length(raw_payload) > 0), "
        "encoding TEXT NOT NULL CHECK(encoding IN ('json', 'protobuf')), "
        "received_at_us INTEGER NOT NULL, owner_id TEXT)"
    )
    await connection.execute(
        "CREATE INDEX analytics_raw_batches_receipt ON analytics_raw_batches (received_at_us)"
    )
    await connection.execute("ALTER TABLE analytics_logs ADD COLUMN raw_batch_id INTEGER")
    await connection.execute(
        "ALTER TABLE analytics_logs ADD COLUMN raw_record_index INTEGER CHECK("
        "(raw_batch_id IS NULL AND raw_record_index IS NULL) OR "
        "(raw_batch_id IS NOT NULL AND raw_record_index IS NOT NULL AND raw_record_index >= 0))"
    )
    await connection.execute(
        "CREATE UNIQUE INDEX analytics_logs_raw_record "
        "ON analytics_logs (raw_batch_id, raw_record_index)"
    )


async def _migrate_activity(connection: aiosqlite.Connection) -> None:
    await connection.execute("ALTER TABLE analytics_logs ADD COLUMN activity_kind TEXT")
    await connection.execute("ALTER TABLE analytics_logs ADD COLUMN outcome TEXT")
    async with connection.execute(
        "SELECT DISTINCT source, event_name, tool_name FROM analytics_logs"
    ) as cursor:
        combinations = await cursor.fetchall()
    for source, event, tool in combinations:
        enrichment = classify_activity(
            source or "", event or "", tool or "", "unknown", "unknown",
        )
        if enrichment:
            await connection.execute(
                "UPDATE analytics_logs SET activity_kind = ?, outcome = ? "
                "WHERE source IS ? AND event_name IS ? AND tool_name IS ?",
                (
                    enrichment[LogDimension.ACTIVITY_KIND],
                    enrichment.get(LogDimension.OUTCOME),
                    source, event, tool,
                ),
            )
