import asyncio
from pathlib import Path

import aiosqlite
import pytest

from umbod.infrastructure.telemetry import create_sqlite_analytics_runtime
from umbod.infrastructure.telemetry.sqlite import database


@pytest.mark.asyncio
async def test_cancelled_readiness_releases_connection_and_can_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "analytics.sqlite3"
    runtime = create_sqlite_analytics_runtime(path, ())
    entered = asyncio.Event()
    proceed = asyncio.Event()
    prepare_schema = database.ensure_schema

    async def delayed_schema(connection: aiosqlite.Connection) -> None:
        entered.set()
        await proceed.wait()
        await prepare_schema(connection)

    monkeypatch.setattr(database, "ensure_schema", delayed_schema)
    preparing = asyncio.create_task(runtime.ensure_ready())
    await asyncio.wait_for(entered.wait(), timeout=2)
    preparing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await preparing
    proceed.set()
    await runtime.ensure_ready()
    await runtime.shutdown()
    async with aiosqlite.connect(path, timeout=0) as connection:
        await connection.execute("BEGIN IMMEDIATE")
        await connection.rollback()
