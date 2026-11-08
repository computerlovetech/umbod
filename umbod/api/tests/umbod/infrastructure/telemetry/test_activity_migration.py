from pathlib import Path

import aiosqlite
import pytest

from umbod.core.telemetry.analytics import TelemetryAnalyticsUnavailable
from umbod.infrastructure.telemetry.sqlite.database import SqliteAnalyticsRuntime
from umbod.infrastructure.telemetry.sqlite.schema import APPLICATION_ID


async def _legacy_database(path: Path, application_id: int, version: int, malformed: bool) -> None:
    async with aiosqlite.connect(path) as connection:
        await connection.execute(
            "CREATE TABLE analytics_logs (occurred_at_us INTEGER NOT NULL, "
            "owner_id TEXT, source TEXT, event_name TEXT, severity TEXT, "
            "session_id TEXT, tool_name TEXT)"
            if not malformed else "CREATE TABLE analytics_logs (wrong TEXT)"
        )
        if not malformed:
            await connection.execute(
                "CREATE INDEX analytics_logs_time_owner ON analytics_logs (occurred_at_us, owner_id)"
            )
            await connection.execute("CREATE INDEX custom_event_index ON analytics_logs (event_name)")
            await connection.executemany(
                "INSERT INTO analytics_logs VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (1, "owner", "claude-code", "tool_result", "ERROR", "session", "Read"),
                    (2, None, "codex", "tool_result", "INFO", "session", "apply_patch"),
                    (3, None, "custom", "codex.skill_invocation", None, None, None),
                    (4, None, "custom", "tool_result", "ERROR", None, "Read"),
                    (5, None, None, None, None, None, None),
                    (6, None, None, "codex.tool_result", None, None, None),
                    (7, None, "claude-code-desktop", "skill_activated", None, None, None),
                ],
            )
        await connection.execute(f"PRAGMA application_id = {application_id}")
        await connection.execute(f"PRAGMA user_version = {version}")
        await connection.commit()


@pytest.mark.asyncio
async def test_version_one_backfill_preserves_raw_rows_indexes_and_reopens_idempotently(tmp_path: Path) -> None:
    path = tmp_path / "analytics.sqlite3"
    await _legacy_database(path, APPLICATION_ID, 1, False)
    async with aiosqlite.connect(path) as connection:
        async with connection.execute("SELECT * FROM analytics_logs ORDER BY occurred_at_us") as cursor:
            original_rows = await cursor.fetchall()
        async with connection.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' ORDER BY name") as cursor:
            original_indexes = await cursor.fetchall()
    for _ in range(2):
        runtime = SqliteAnalyticsRuntime(path, ())
        try:
            await runtime.ensure_ready()
            async with runtime.connection() as connection:
                async with connection.execute("SELECT * FROM analytics_logs ORDER BY occurred_at_us") as cursor:
                    rows = await cursor.fetchall()
                async with connection.execute("PRAGMA user_version") as cursor:
                    assert (await cursor.fetchone())[0] == 3
                async with connection.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' ORDER BY name") as cursor:
                    assert [tuple(row) for row in await cursor.fetchall()] == original_indexes
        finally:
            await runtime.shutdown()
        assert [row[:7] for row in rows] == original_rows
        assert [row[9] for row in rows] == [None] * len(original_rows)
        assert [row[7:9] for row in rows] == [
            ("file_read", "unknown"), ("tool_call", "unknown"),
            ("skill_activation", None), (None, None), (None, None),
            ("tool_call", "unknown"), ("skill_activation", None),
        ]


@pytest.mark.asyncio
async def test_backfill_failure_rolls_back_added_columns_and_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "analytics.sqlite3"
    await _legacy_database(path, APPLICATION_ID, 1, False)
    async with aiosqlite.connect(path) as connection:
        await connection.execute(
            "CREATE TRIGGER reject_backfill BEFORE UPDATE ON analytics_logs "
            "BEGIN SELECT RAISE(ABORT, 'backfill rejected'); END"
        )
        await connection.commit()
    original = path.read_bytes()
    runtime = SqliteAnalyticsRuntime(path, ())
    try:
        with pytest.raises(TelemetryAnalyticsUnavailable):
            await runtime.ensure_ready()
    finally:
        await runtime.shutdown()
    assert path.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("application_id,version,malformed", [
    (APPLICATION_ID, 1, True),
    (APPLICATION_ID + 1, 1, False),
    (APPLICATION_ID, 3, False),
    (APPLICATION_ID, 4, False),
    (APPLICATION_ID, 0, False),
])
async def test_invalid_legacy_database_is_not_mutated(
    tmp_path: Path, application_id: int, version: int, malformed: bool,
) -> None:
    path = tmp_path / "analytics.sqlite3"
    await _legacy_database(path, application_id, version, malformed)
    original = path.read_bytes()
    runtime = SqliteAnalyticsRuntime(path, ())
    try:
        with pytest.raises(TelemetryAnalyticsUnavailable):
            await runtime.ensure_ready()
    finally:
        await runtime.shutdown()
    assert path.read_bytes() == original
