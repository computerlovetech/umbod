import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from umbod.config.app import AppConfig
from umbod.core.telemetry.analytics import TelemetryAnalyticsUnavailable
from umbod.core.telemetry.analytics.backfill import (
    BackfillSelectionLimitExceeded,
    BackfillWindow,
)
from umbod.core.telemetry.analytics.replay import ReplayArchiveUnavailable, ReplayBatch, ReplaySummary
from umbod.infrastructure import create_configured_analytics_runtime, create_log_archive_backfill
from umbod.infrastructure.telemetry import backfill_composition
from umbod.infrastructure.telemetry.sqlite.schema import APPLICATION_ID
from umbod.infrastructure.telemetry.sqlite.values import to_microseconds

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 3, 1, 12, 14, 15, 123456, tzinfo=timezone.utc)
_CUTOFF = _NOW - timedelta(days=1)
_START = _NOW - timedelta(hours=1)
_RECEIPTS = (_NOW, _START, _CUTOFF, _START, _START + timedelta(microseconds=1))
_BATCH = ReplayBatch(batch_id=2)
_EXPIRED_BATCH = ReplayBatch(batch_id=3)
_OWNER = "trusted-owner"


def _config(database_path: Path) -> AppConfig:
    return AppConfig(telemetry_analytics={
        "enabled": True, "sqlite_path": str(database_path), "raw_archive_retention_days": 1,
    })


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "analytics ?# archive.sqlite3"


def _now() -> datetime:
    return _NOW


@pytest_asyncio.fixture
async def archive(database_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AppConfig]:
    config = _config(database_path)
    monkeypatch.setattr(backfill_composition, "utc_now", _now)
    server = create_configured_analytics_runtime(config)
    await server.ensure_ready()
    try:
        fixture = Path(__file__).parents[2] / "rest" / "telemetry" / "fixtures" / "codex_tool_result.json"
        payload = json.dumps(json.loads(fixture.read_bytes())["payload"]).encode()
        with closing(sqlite3.connect(database_path)) as connection, connection:
            connection.executemany(
                "INSERT INTO analytics_raw_batches (raw_payload, encoding, received_at_us, owner_id) "
                "VALUES (?, 'json', ?, ?)",
                [(payload, to_microseconds(receipt), _OWNER) for receipt in _RECEIPTS],
            )
            connection.executemany(
                "INSERT INTO analytics_logs (occurred_at_us, event_name, raw_batch_id, raw_record_index) "
                "VALUES (0, 'prior', ?, ?)", [(2, 0), (4, 0), (None, None)],
            )
        yield config
    finally:
        await server.shutdown()


def _snapshot(database_path: Path) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    with closing(sqlite3.connect(database_path)) as connection:
        raw_batches = connection.execute("SELECT * FROM analytics_raw_batches ORDER BY id").fetchall()
        logs = connection.execute("SELECT * FROM analytics_logs ORDER BY rowid").fetchall()
    return raw_batches, logs


@pytest.mark.parametrize("apply", [False, True])
async def test_backfill_missing_database_does_not_create_directory(tmp_path: Path, apply: bool) -> None:
    with pytest.raises(TelemetryAnalyticsUnavailable, match="backfill is unavailable"):
        async with create_log_archive_backfill(_config(tmp_path / "missing" / "analytics.sqlite3"), apply=apply):
            pass

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("version", [0, 3, 4])
async def test_apply_backfill_does_not_initialize_or_migrate_unrecognized_schema(
    database_path: Path, version: int,
) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        if version:
            connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {version}")
    before = database_path.read_bytes()

    with pytest.raises(TelemetryAnalyticsUnavailable, match="backfill is unavailable"):
        async with create_log_archive_backfill(_config(database_path), apply=True):
            pass

    assert database_path.read_bytes() == before


async def test_selection_uses_inclusive_start_exclusive_end_and_orders_ties(archive: AppConfig) -> None:
    async with create_log_archive_backfill(archive, apply=False) as store:
        batches = await store.select(BackfillWindow(start=_START, end=_NOW, limit=3))

    assert batches == (_BATCH, ReplayBatch(batch_id=4), ReplayBatch(batch_id=5))


async def test_selection_only_reads_metadata_for_archived_batches(archive: AppConfig, database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("UPDATE analytics_raw_batches SET raw_payload = ? WHERE id = 2", (b"invalid JSON",))

    async with create_log_archive_backfill(archive, apply=False) as store:
        batches = await store.select(BackfillWindow(start=_START, end=_NOW, limit=3))

    assert _BATCH in batches


async def test_selection_excludes_retention_boundary(archive: AppConfig) -> None:
    async with create_log_archive_backfill(archive, apply=False) as store:
        batches = await store.select(BackfillWindow(start=_CUTOFF, end=_START, limit=1))

    assert batches == ()


async def test_apply_selection_overflow_leaves_existing_archive_and_projections_untouched(
    archive: AppConfig, database_path: Path,
) -> None:
    before = _snapshot(database_path)
    async with create_log_archive_backfill(archive, apply=True) as store:
        with pytest.raises(BackfillSelectionLimitExceeded):
            await store.select(BackfillWindow(start=_START, end=_NOW, limit=2))

    assert _snapshot(database_path) == before


async def test_read_only_backfill_returns_safe_summary_and_cannot_apply(
    archive: AppConfig, database_path: Path,
) -> None:
    before = _snapshot(database_path)
    async with create_log_archive_backfill(archive, apply=False) as store:
        assert await store.preview(_BATCH) == ReplaySummary(batch_id=2, received_at=_START, record_count=1)
        with pytest.raises(TelemetryAnalyticsUnavailable, match="read-only"):
            await store.apply(_BATCH)

    assert _snapshot(database_path) == before


@pytest.mark.parametrize("operation", ["preview", "apply"])
async def test_backfill_rechecks_retention_before_replay(
    archive: AppConfig, database_path: Path, operation: str,
) -> None:
    before = _snapshot(database_path)
    async with create_log_archive_backfill(archive, apply=True) as store:
        access = {"preview": store.preview, "apply": store.apply}
        with pytest.raises(ReplayArchiveUnavailable):
            await access[operation](_EXPIRED_BATCH)

    assert _snapshot(database_path) == before


async def test_repeated_backfill_only_replaces_requested_projection_with_stored_owner(
    archive: AppConfig, database_path: Path,
) -> None:
    raw_before, logs_before = _snapshot(database_path)
    summary = ReplaySummary(batch_id=2, received_at=_START, record_count=1)
    async with create_log_archive_backfill(archive, apply=True) as store:
        assert await store.apply(_BATCH) == summary
        assert await store.apply(_BATCH) == summary

    raw_after, logs_after = _snapshot(database_path)
    assert raw_after == raw_before
    assert logs_after[:-1] == logs_before[1:]
    assert logs_after[-1][1] == _OWNER
    assert logs_after[-1][-2:] == (2, 0)
