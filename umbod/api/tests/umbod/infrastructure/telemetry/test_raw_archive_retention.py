import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import pytest

from umbod.config.app import AppConfig
from umbod.config.defaults import TELEMETRY_ANALYTICS_RAW_ARCHIVE_RETENTION_DAYS
from umbod.core.telemetry.analytics import (
    LogCountQuery,
    NoTimeBuckets,
    OwnersScope,
    PaginationQuery,
    TimeRange,
)
from umbod.infrastructure.telemetry.composition import create_configured_analytics_runtime
from umbod.infrastructure.telemetry.sqlite import database
from umbod.infrastructure.telemetry.sqlite.database import SqliteAnalyticsRuntime
from umbod.infrastructure.telemetry.sqlite.retention import expire_raw_archives
from umbod.infrastructure.telemetry.sqlite.values import to_microseconds

NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)
LOG_TIME = NOW - timedelta(days=365)
OWNER_ID = "archive-owner"


async def _seed_archives(path: Path, now: datetime, receipts: tuple[datetime, ...]) -> None:
    runtime = SqliteAnalyticsRuntime.with_retention(
        path, (), TELEMETRY_ANALYTICS_RAW_ARCHIVE_RETENTION_DAYS, lambda: now,
    )
    try:
        async with runtime.connection() as connection:
            for receipt in receipts:
                async with connection.execute(
                    "INSERT INTO analytics_raw_batches "
                    "(raw_payload, encoding, received_at_us, owner_id) VALUES (?, ?, ?, ?)",
                    (b"{}", "json", to_microseconds(receipt), OWNER_ID),
                ) as cursor:
                    batch_id = cursor.lastrowid
                await connection.execute(
                    "INSERT INTO analytics_logs "
                    "(occurred_at_us, owner_id, raw_batch_id, raw_record_index) VALUES (?, ?, ?, 0)",
                    (to_microseconds(LOG_TIME), OWNER_ID, batch_id),
                )
            await connection.commit()
    finally:
        await runtime.shutdown()


async def _archive_receipts(path: Path) -> list[int]:
    async with aiosqlite.connect(path) as connection:
        async with connection.execute(
            "SELECT received_at_us FROM analytics_raw_batches ORDER BY received_at_us"
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]


@pytest.mark.asyncio
async def test_startup_expires_at_receipt_cutoff_without_changing_owned_counts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "analytics.sqlite3"
    cutoff = NOW - timedelta(days=2)
    expired = cutoff - timedelta(microseconds=1)
    unexpired = cutoff + timedelta(microseconds=1)
    await _seed_archives(path, NOW, (expired, cutoff, unexpired))
    runtime = SqliteAnalyticsRuntime.with_retention(path, (), 2, lambda: NOW)
    query = LogCountQuery(
        scope=OwnersScope(kind="owners", owner_ids=(OWNER_ID,)),
        time_range=TimeRange(start=LOG_TIME, end=NOW),
        filters=(),
        group_by=(),
        bucketing=NoTimeBuckets(kind="none"),
        pagination=PaginationQuery(limit=10, offset=0),
    )
    try:
        await runtime.ensure_ready()
        assert await _archive_receipts(path) == [to_microseconds(unexpired)]
        result = await runtime.create_reader().count_logs(query)
        assert result.rows[0].count == 3
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_configured_analytics_expires_existing_archives_when_capture_is_off(
    tmp_path: Path,
) -> None:
    path = tmp_path / "analytics.sqlite3"
    now = datetime.now(timezone.utc)
    await _seed_archives(path, now, (now - timedelta(days=7),))
    config = AppConfig.model_validate({
        "telemetry_analytics": {
            "enabled": True,
            "sqlite_path": str(path),
            "raw_archive_enabled": False,
            "raw_archive_retention_days": 1,
        },
    })
    runtime = create_configured_analytics_runtime(config)
    try:
        await runtime.ensure_ready()
        assert await _archive_receipts(path) == []
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_hourly_worker_expires_newly_stale_archives_while_ingestion_is_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "analytics.sqlite3"
    receipt = NOW - timedelta(days=1)
    await _seed_archives(path, NOW, (receipt,))
    monkeypatch.setattr(database, "ARCHIVE_SWEEP_INTERVAL_SECONDS", 0.01)
    now = NOW
    runtime = SqliteAnalyticsRuntime.with_retention(path, (), 2, lambda: now)
    try:
        await asyncio.gather(runtime.ensure_ready(), runtime.ensure_ready())
        assert await _archive_receipts(path) == [to_microseconds(receipt)]
        now += timedelta(days=1)
        async with asyncio.timeout(2):
            while await _archive_receipts(path):
                await asyncio.sleep(0.01)
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_failed_startup_sweep_does_not_block_readiness_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "analytics.sqlite3"
    receipt = NOW - timedelta(days=3)
    await _seed_archives(path, NOW, (receipt,))
    monkeypatch.setattr(database, "ARCHIVE_SWEEP_RETRY_SECONDS", 0.01)
    async with aiosqlite.connect(path) as connection:
        await connection.execute(
            "CREATE TRIGGER reject_expiry BEFORE DELETE ON analytics_raw_batches "
            "BEGIN SELECT RAISE(ABORT, 'private diagnostic'); END"
        )
    runtime = SqliteAnalyticsRuntime.with_retention(path, (), 2, lambda: NOW)
    try:
        await runtime.ensure_ready()
        assert await _archive_receipts(path) == [to_microseconds(receipt)]
        async with aiosqlite.connect(path) as connection:
            await connection.execute("DROP TRIGGER reject_expiry")
        async with asyncio.timeout(2):
            while await _archive_receipts(path):
                await asyncio.sleep(0.01)
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_active_sweep_and_releases_its_write_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "analytics.sqlite3"
    await _seed_archives(path, NOW, (NOW,))
    running = asyncio.Event()
    stopped = asyncio.Event()
    startup_complete = False

    async def block_scheduled_sweep(connection: aiosqlite.Connection, cutoff_us: int) -> None:
        if not startup_complete:
            await expire_raw_archives(connection, cutoff_us)
            return
        async with connection.execute("BEGIN IMMEDIATE"):
            running.set()
            try:
                await asyncio.Future[None]()
            finally:
                stopped.set()

    monkeypatch.setattr(database, "ARCHIVE_SWEEP_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(database, "expire_raw_archives", block_scheduled_sweep)
    runtime = SqliteAnalyticsRuntime.with_retention(path, (), 2, lambda: NOW)
    try:
        await runtime.ensure_ready()
        startup_complete = True
        await asyncio.wait_for(running.wait(), timeout=2)
    finally:
        await asyncio.wait_for(runtime.shutdown(), timeout=2)
    assert stopped.is_set()
    async with aiosqlite.connect(path, timeout=0) as connection:
        await connection.execute("BEGIN IMMEDIATE")
        await connection.rollback()
