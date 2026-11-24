import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import pytest
import pytest_asyncio

from umbod.config.app import AppConfig
from umbod.core.telemetry import TelemetrySignal
from umbod.core.telemetry.analytics import (
    ArchivedLogWriteBatch,
    InstanceScope,
    LogCountQuery,
    LogWriteBatch,
    NoTimeBuckets,
    OwnedLog,
    PaginationQuery,
    TelemetryAnalyticsUnavailable,
    TimeRange,
)
from umbod.core.telemetry.analytics.replay import (
    ReplayArchiveUnavailable,
    ReplayBatch,
    ReplayNormalizationFailed,
    ReplaySummary,
)
from umbod.core.telemetry.analytics.write_models import LogArchiveSource
from umbod.core.telemetry.adapters.otlp_normalization import normalize_archived_logs
from umbod.core.telemetry.adapters.otlp_validation import parse_message
from umbod.infrastructure import (
    create_configured_analytics_runtime,
    create_disabled_analytics_runtime,
    create_log_archive_replay,
    create_log_archive_replay_with_normalizer,
)
from umbod.infrastructure.telemetry.sqlite.database import SqliteAnalyticsRuntime
from umbod.infrastructure.telemetry.sqlite.values import to_microseconds

pytestmark = pytest.mark.asyncio

_RECEIPT = datetime(2026, 3, 1, 12, 14, 15, 123456, tzinfo=timezone.utc)
_BATCH = ReplayBatch(batch_id=1)
_OWNER = OwnedLog(kind="owned", owner_id="verified-owner")
_SKILL = "private-skill-marker"


@dataclass
class ReplayClock:
    current_time: datetime

    def now(self) -> datetime:
        return self.current_time


@pytest.fixture
def clock() -> ReplayClock:
    return ReplayClock(_RECEIPT + timedelta(hours=1))


@pytest_asyncio.fixture
async def runtime(tmp_path: Path, clock: ReplayClock) -> AsyncIterator[SqliteAnalyticsRuntime]:
    database = SqliteAnalyticsRuntime.with_retention(
        tmp_path / "analytics.sqlite3", (), raw_archive_retention_days=1, clock=clock.now,
    )
    try:
        await database.ensure_ready()
        yield database
    finally:
        await database.shutdown()


def _codex_batch(encoding: Literal["json", "protobuf"]) -> ArchivedLogWriteBatch:
    fixture_path = Path(__file__).parents[2] / "rest" / "telemetry" / "fixtures" / "codex_tool_result.json"
    payload = json.loads(fixture_path.read_bytes())["payload"]
    payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"].append({
        "eventName": "codex.skill_invocation",
        "attributes": [
            {"key": "skill.name", "value": {"stringValue": _SKILL}},
            {"key": "owner_id", "value": {"stringValue": "unverified-owner"}},
        ],
    })
    raw = (
        json.dumps(payload, indent=2).encode()
        if encoding == "json"
        else parse_message(TelemetrySignal.LOGS, payload).SerializeToString()
    )
    source = LogArchiveSource(
        raw_payload=raw, encoding=encoding, received_at=_RECEIPT, owner=_OWNER,
    )
    return ArchivedLogWriteBatch(
        raw_payload=raw, encoding=encoding, received_at=_RECEIPT, owner=_OWNER,
        records=normalize_archived_logs(source).records,
    )


async def _analytics_count(runtime: SqliteAnalyticsRuntime) -> int:
    query = LogCountQuery(
        scope=InstanceScope(kind="instance"),
        time_range=TimeRange(start=datetime(1970, 1, 1, tzinfo=timezone.utc), end=_RECEIPT + timedelta(days=1)),
        filters=(), group_by=(), bucketing=NoTimeBuckets(kind="none"),
        pagination=PaginationQuery(limit=10, offset=0),
    )
    result = await runtime.create_reader().count_logs(query)
    return sum(row.count for row in result.rows)


async def _log_rows(runtime: SqliteAnalyticsRuntime) -> list[tuple[object, ...]]:
    async with runtime.connection() as connection:
        async with connection.execute(
            "SELECT * FROM analytics_logs ORDER BY raw_batch_id, raw_record_index"
        ) as cursor:
            return [tuple(row) for row in await cursor.fetchall()]


@pytest.mark.parametrize("encoding", ["json", "protobuf"])
async def test_repeat_replay_preserves_count_and_stored_archive(
    runtime: SqliteAnalyticsRuntime, encoding: Literal["json", "protobuf"],
) -> None:
    batch = _codex_batch(encoding)
    writer = runtime.create_writer()
    await writer.append_logs(LogWriteBatch(records=batch.records))
    await writer.append_logs(batch)
    await writer.append_logs(batch)
    replay = create_log_archive_replay(runtime)
    before = await _log_rows(runtime)

    assert await replay.apply(_BATCH) == ReplaySummary(batch_id=1, received_at=_RECEIPT, record_count=2)
    assert await replay.apply(_BATCH) == ReplaySummary(batch_id=1, received_at=_RECEIPT, record_count=2)

    assert await _analytics_count(runtime) == 6
    assert await _log_rows(runtime) == before
    async with runtime.connection() as connection:
        async with connection.execute(
            "SELECT raw_payload, encoding, received_at_us, owner_id "
            "FROM analytics_raw_batches WHERE id = 1"
        ) as cursor:
            archived = tuple(await cursor.fetchone())
        async with connection.execute(
            "SELECT occurred_at_us, owner_id, normalization_json, raw_record_index "
            "FROM analytics_logs WHERE raw_batch_id = 1 ORDER BY raw_record_index"
        ) as cursor:
            rows = await cursor.fetchall()
    assert archived == (batch.raw_payload, encoding, to_microseconds(_RECEIPT), _OWNER.owner_id)
    assert _SKILL.encode() in archived[0]
    assert [row[3] for row in rows] == [0, 1]
    assert rows[1][0] == to_microseconds(_RECEIPT)
    for _, owner, normalization, _ in rows:
        assert owner == _OWNER.owner_id
        assert json.loads(normalization)["timestamps"]["receipt_ns"] == to_microseconds(_RECEIPT) * 1000
        assert _SKILL not in normalization
        assert "skill.name" not in normalization


async def test_preview_reports_only_safe_metadata_and_leaves_current_rows(
    runtime: SqliteAnalyticsRuntime,
) -> None:
    await runtime.create_writer().append_logs(_codex_batch("json"))
    async with runtime.connection() as connection:
        async with connection.execute("UPDATE analytics_logs SET event_name = 'prior'"):
            await connection.commit()
    before = await _log_rows(runtime)

    summary = await create_log_archive_replay(runtime).preview(_BATCH)

    assert summary.model_dump() == {"batch_id": 1, "received_at": _RECEIPT, "record_count": 2}
    assert await _log_rows(runtime) == before


async def test_apply_replaces_only_selected_batch_rows(runtime: SqliteAnalyticsRuntime) -> None:
    batch = _codex_batch("json")
    writer = runtime.create_writer()
    await writer.append_logs(LogWriteBatch(records=batch.records))
    await writer.append_logs(batch)
    await writer.append_logs(batch)
    before = await _log_rows(runtime)
    async with runtime.connection() as connection:
        async with connection.execute(
            "UPDATE analytics_logs SET event_name = 'prior' WHERE raw_batch_id = 1"
        ):
            await connection.commit()

    await create_log_archive_replay(runtime).apply(_BATCH)

    assert await _log_rows(runtime) == before


async def test_apply_rejects_batch_that_expired_after_preview(
    runtime: SqliteAnalyticsRuntime, clock: ReplayClock,
) -> None:
    await runtime.create_writer().append_logs(_codex_batch("json"))
    replay = create_log_archive_replay(runtime)
    before = await _log_rows(runtime)
    await replay.preview(_BATCH)
    clock.current_time = _RECEIPT + timedelta(days=1)

    with pytest.raises(ReplayArchiveUnavailable, match="Archived log batch is unavailable"):
        await replay.apply(_BATCH)
    with pytest.raises(ReplayArchiveUnavailable, match="Archived log batch is unavailable"):
        await replay.preview(_BATCH)

    assert await _log_rows(runtime) == before


async def test_expiry_while_applying_rolls_back_replacement(
    runtime: SqliteAnalyticsRuntime, clock: ReplayClock,
) -> None:
    await runtime.create_writer().append_logs(_codex_batch("json"))
    async with runtime.connection() as connection:
        async with connection.execute("UPDATE analytics_logs SET event_name = 'prior'"):
            await connection.commit()
    before = await _log_rows(runtime)

    def crosses_cutoff(source: LogArchiveSource) -> LogWriteBatch:
        clock.current_time = _RECEIPT + timedelta(days=1)
        return normalize_archived_logs(source)

    with pytest.raises(ReplayArchiveUnavailable, match="Archived log batch is unavailable"):
        await create_log_archive_replay_with_normalizer(runtime, crosses_cutoff).apply(_BATCH)

    assert await _log_rows(runtime) == before


async def test_parse_failure_does_not_change_rows_or_expose_payload(runtime: SqliteAnalyticsRuntime) -> None:
    await runtime.create_writer().append_logs(_codex_batch("json"))
    async with runtime.connection() as connection:
        async with connection.execute(
            "UPDATE analytics_raw_batches SET raw_payload = ?", (_SKILL.encode(),)
        ):
            await connection.commit()
    before = await _log_rows(runtime)

    with pytest.raises(ReplayNormalizationFailed, match="^Archived log normalization failed$"):
        await create_log_archive_replay(runtime).apply(_BATCH)

    assert await _log_rows(runtime) == before


async def test_preview_does_not_initialize_configured_runtime(tmp_path: Path) -> None:
    database_path = tmp_path / "analytics.sqlite3"
    config = AppConfig.model_validate({
        "telemetry_analytics": {"enabled": True, "sqlite_path": str(database_path)},
    })
    runtime = create_configured_analytics_runtime(config)
    try:
        replay = create_log_archive_replay(runtime)
        with pytest.raises(TelemetryAnalyticsUnavailable):
            await replay.preview(_BATCH)
        assert not database_path.exists()

        await runtime.ensure_ready()
        with pytest.raises(ReplayArchiveUnavailable):
            await replay.preview(_BATCH)
    finally:
        await runtime.shutdown()


async def test_disabled_runtime_has_no_replay() -> None:
    with pytest.raises(TelemetryAnalyticsUnavailable, match="^Telemetry archive replay is unavailable$"):
        create_log_archive_replay(create_disabled_analytics_runtime())


async def test_partial_write_failure_restores_prior_batch(runtime: SqliteAnalyticsRuntime) -> None:
    await runtime.create_writer().append_logs(_codex_batch("protobuf"))
    async with runtime.connection() as connection:
        async with connection.execute("UPDATE analytics_logs SET event_name = 'prior'"):
            await connection.commit()
        async with connection.execute(
            "CREATE TRIGGER reject_second_replayed_record BEFORE INSERT ON analytics_logs "
            "WHEN NEW.raw_record_index = 1 "
            "BEGIN SELECT RAISE(ABORT, 'partial write rejected'); END"
        ):
            await connection.commit()
    before = await _log_rows(runtime)

    with pytest.raises(TelemetryAnalyticsUnavailable, match="^Telemetry analytics is unavailable$"):
        await create_log_archive_replay(runtime).apply(_BATCH)

    assert await _log_rows(runtime) == before
