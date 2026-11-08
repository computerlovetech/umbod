import aiosqlite

from umbod.core.telemetry.analytics import LogDimension
from umbod.core.telemetry.analytics.activity import classify_activity

APPLICATION_ID = 1431126350
SCHEMA_VERSION = 2
LEGACY_COLUMNS = (
    ("occurred_at_us", "INTEGER", 1),
    ("owner_id", "TEXT", 0),
    ("source", "TEXT", 0),
    ("event_name", "TEXT", 0),
    ("severity", "TEXT", 0),
    ("session_id", "TEXT", 0),
    ("tool_name", "TEXT", 0),
)
COLUMNS = LEGACY_COLUMNS + (("activity_kind", "TEXT", 0), ("outcome", "TEXT", 0))


async def ensure_schema(connection: aiosqlite.Connection) -> None:
    async with connection.execute("PRAGMA application_id") as cursor:
        application_id = (await cursor.fetchone())[0]
    async with connection.execute("PRAGMA user_version") as cursor:
        version = (await cursor.fetchone())[0]
    async with connection.execute(
        "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
    ) as cursor:
        objects = await cursor.fetchall()
    if application_id == 0 and version == 0 and not objects:
        await connection.execute(
            "CREATE TABLE analytics_logs (occurred_at_us INTEGER NOT NULL, "
            "owner_id TEXT, source TEXT, event_name TEXT, severity TEXT, "
            "session_id TEXT, tool_name TEXT, activity_kind TEXT, outcome TEXT)"
        )
        await connection.execute(
            "CREATE INDEX analytics_logs_time_owner "
            "ON analytics_logs (occurred_at_us, owner_id)"
        )
        await connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    elif application_id != APPLICATION_ID or version not in (1, SCHEMA_VERSION):
        raise ValueError("Unrecognized analytics database")
    async with connection.execute("PRAGMA table_info(analytics_logs)") as cursor:
        columns = tuple((row[1], row[2], row[3]) for row in await cursor.fetchall())
    if version == 1:
        if columns != LEGACY_COLUMNS:
            raise ValueError("Invalid analytics schema")
        await _migrate_activity(connection)
    elif columns != COLUMNS:
        raise ValueError("Invalid analytics schema")


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
    await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
