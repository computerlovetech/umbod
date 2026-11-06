import asyncio
from pathlib import Path

import aiosqlite
import pytest

from umbod.core.telemetry.analytics import TelemetryAnalyticsUnavailable
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


@pytest.mark.asyncio
async def test_repeatedly_cancelled_shutdown_drains_active_operation(
    tmp_path: Path,
) -> None:
    runtime = database.SqliteAnalyticsRuntime(tmp_path / "analytics.sqlite3", ())
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold_connection() -> None:
        async with runtime.connection() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            entered.set()
            await release.wait()

    holding = asyncio.create_task(hold_connection())
    stopping = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        stopping = asyncio.create_task(runtime.shutdown())
        await asyncio.sleep(0)
        stopping.cancel()
        await asyncio.sleep(0)
        stopping.cancel()
        await asyncio.sleep(0)
        assert not stopping.done()
        release.set()
        await asyncio.wait_for(holding, timeout=2)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(stopping, timeout=2)
        with pytest.raises(TelemetryAnalyticsUnavailable):
            await runtime.ensure_ready()
    finally:
        release.set()
        await holding
        if stopping is not None:
            await asyncio.gather(stopping, return_exceptions=True)
        await runtime.shutdown()
