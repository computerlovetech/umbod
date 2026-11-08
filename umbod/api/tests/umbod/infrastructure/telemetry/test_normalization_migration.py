import sqlite3
from pathlib import Path

import aiosqlite
import pytest

from umbod.core.telemetry.analytics import TelemetryAnalyticsUnavailable
from umbod.infrastructure.telemetry.sqlite import database
from umbod.infrastructure.telemetry.sqlite.database import SqliteAnalyticsRuntime
from umbod.infrastructure.telemetry.sqlite.schema import APPLICATION_ID, ensure_schema


async def _version_two_database(path: Path) -> None:
    async with aiosqlite.connect(path) as connection:
        await connection.execute(
            "CREATE TABLE analytics_logs (occurred_at_us INTEGER NOT NULL, "
            "owner_id TEXT, source TEXT, event_name TEXT, severity TEXT, "
            "session_id TEXT, tool_name TEXT, activity_kind TEXT, outcome TEXT)"
        )
        await connection.execute(
            "CREATE INDEX analytics_logs_time_owner ON analytics_logs (occurred_at_us, owner_id)"
        )
        await connection.execute(
            "CREATE INDEX custom_session_index ON analytics_logs (session_id)"
        )
        await connection.executemany(
            "INSERT INTO analytics_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "owner", "codex", "codex.tool_result", "INFO", "session", "apply_patch", "file_edit", "success"),
                (2, None, "codex_exec", "event otel/src/events/session_telemetry.rs:375", "INFO", None, None, None, None),
            ],
        )
        await connection.execute(
            "CREATE TRIGGER reject_reclassification BEFORE UPDATE ON analytics_logs "
            "BEGIN SELECT RAISE(ABORT, 'historical records must not change'); END"
        )
        await connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        await connection.execute("PRAGMA user_version = 2")
        await connection.commit()


@pytest.mark.asyncio
async def test_version_two_upgrade_preserves_rows_indexes_and_unknown_evidence_on_reopen(tmp_path: Path) -> None:
    path = tmp_path / "analytics.sqlite3"
    await _version_two_database(path)
    async with aiosqlite.connect(path) as connection:
        async with connection.execute("SELECT rowid, * FROM analytics_logs ORDER BY rowid") as cursor:
            original_rows = await cursor.fetchall()
        async with connection.execute("SELECT name, sql FROM sqlite_master ORDER BY name") as cursor:
            original_objects = await cursor.fetchall()
    for _ in range(2):
        runtime = SqliteAnalyticsRuntime(path, ())
        try:
            await runtime.ensure_ready()
            async with runtime.connection() as connection:
                async with connection.execute("PRAGMA user_version") as cursor:
                    assert (await cursor.fetchone())[0] == 3
                async with connection.execute("SELECT rowid, * FROM analytics_logs ORDER BY rowid") as cursor:
                    rows = await cursor.fetchall()
                async with connection.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type != 'table' ORDER BY name"
                ) as cursor:
                    objects = await cursor.fetchall()
        finally:
            await runtime.shutdown()
        assert [tuple(row[:-1]) for row in rows] == original_rows
        assert [row[-1] for row in rows] == [None, None]
        assert [tuple(row) for row in objects] == [row for row in original_objects if row[0] != "analytics_logs"]


@pytest.mark.asyncio
async def test_failed_normalization_upgrade_rolls_back_column_and_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "analytics.sqlite3"
    await _version_two_database(path)
    original = path.read_bytes()

    async def fail_after_upgrade(connection: aiosqlite.Connection) -> None:
        await ensure_schema(connection)
        raise sqlite3.OperationalError("schema preparation interrupted")

    monkeypatch.setattr(database, "ensure_schema", fail_after_upgrade)
    runtime = SqliteAnalyticsRuntime(path, ())
    try:
        with pytest.raises(TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"):
            await runtime.ensure_ready()
    finally:
        await runtime.shutdown()
    assert path.read_bytes() == original


@pytest.mark.asyncio
async def test_malformed_version_two_schema_is_rejected_without_modification(tmp_path: Path) -> None:
    path = tmp_path / "analytics.sqlite3"
    async with aiosqlite.connect(path) as connection:
        await connection.execute("CREATE TABLE analytics_logs (wrong TEXT)")
        await connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        await connection.execute("PRAGMA user_version = 2")
        await connection.commit()
    original = path.read_bytes()
    runtime = SqliteAnalyticsRuntime(path, ())
    try:
        with pytest.raises(TelemetryAnalyticsUnavailable):
            await runtime.ensure_ready()
    finally:
        await runtime.shutdown()
    assert path.read_bytes() == original
