import aiosqlite

APPLICATION_ID = 1431126350
SCHEMA_VERSION = 1
COLUMNS = (
    ("occurred_at_us", "INTEGER", 1),
    ("owner_id", "TEXT", 0),
    ("source", "TEXT", 0),
    ("event_name", "TEXT", 0),
    ("severity", "TEXT", 0),
    ("session_id", "TEXT", 0),
    ("tool_name", "TEXT", 0),
)


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
            "session_id TEXT, tool_name TEXT)"
        )
        await connection.execute(
            "CREATE INDEX analytics_logs_time_owner "
            "ON analytics_logs (occurred_at_us, owner_id)"
        )
        await connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    elif application_id != APPLICATION_ID or version != SCHEMA_VERSION:
        raise ValueError("Unrecognized analytics database")
    async with connection.execute("PRAGMA table_info(analytics_logs)") as cursor:
        columns = tuple((row[1], row[2], row[3]) for row in await cursor.fetchall())
    if columns != COLUMNS:
        raise ValueError("Invalid analytics schema")
