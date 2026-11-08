from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
    DimensionGroup,
    LogDimension,
    LogWriteBatch,
    MissingDimensionValue,
    OwnedLog,
    PresentDimensionValue,
    UnownedLog,
)
from umbod.core.telemetry.normalization import UnavailableLogNormalization
from umbod.infrastructure.telemetry.sqlite.database import SqliteAnalyticsRuntime


@pytest.mark.asyncio
async def test_sqlite_analytics_record_columns_survive_runtime_recreation(tmp_path: Path) -> None:
    path = tmp_path / "analytics.sqlite3"
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    owner_id = 'owner 雪 "quoted" \\path'
    values = ("source 雪", 'event "quoted"\\path\nline', "ERROR", "session-1", "", "tool_call", "failure")
    records = (
        AnalyticsLogRecord(
            occurred_at=epoch - timedelta(microseconds=1),
            normalization=UnavailableLogNormalization(kind="unavailable", reason="legacy_or_unspecified"),
            owner=OwnedLog(kind="owned", owner_id=owner_id),
            dimensions=tuple(
                DimensionGroup(dimension=dimension, value=PresentDimensionValue(kind="present", value=value))
                for dimension, value in zip(LogDimension, values, strict=True)
            ),
        ),
        AnalyticsLogRecord(
            occurred_at=epoch,
            normalization=UnavailableLogNormalization(kind="unavailable", reason="legacy_or_unspecified"),            owner=UnownedLog(kind="unowned"),
            dimensions=tuple(
                DimensionGroup(dimension=dimension, value=MissingDimensionValue(kind="missing"))
                for dimension in LogDimension
            ),
        ),
        AnalyticsLogRecord(
            occurred_at=epoch + timedelta(seconds=1, microseconds=234567),
            normalization=UnavailableLogNormalization(kind="unavailable", reason="legacy_or_unspecified"),
            owner=OwnedLog(kind="owned", owner_id=owner_id),
            dimensions=tuple(
                DimensionGroup(dimension=dimension, value=PresentDimensionValue(kind="present", value=""))
                for dimension in LogDimension
            ),
        ),
    )
    writer = SqliteAnalyticsRuntime(path, ())
    try:
        await writer.ensure_ready()
        await writer.create_writer().append_logs(LogWriteBatch(records=records))
    finally:
        await writer.shutdown()

    reader = SqliteAnalyticsRuntime(path, ())
    try:
        await reader.ensure_ready()
        async with reader.connection() as connection:
            async with connection.execute(
                "SELECT occurred_at_us, owner_id, source, event_name, severity, session_id, tool_name, activity_kind, outcome, "
                "typeof(occurred_at_us), typeof(owner_id), typeof(source), typeof(event_name), "
                "typeof(severity), typeof(session_id), typeof(tool_name), typeof(activity_kind), typeof(outcome) "
                "FROM analytics_logs ORDER BY occurred_at_us"
            ) as cursor:
                rows = await cursor.fetchall()
    finally:
        await reader.shutdown()
    assert [tuple(row) for row in rows] == [
        (-1, owner_id, *values, "integer", *("text",) * 8),
        (0, *(None,) * 8, "integer", *("null",) * 8),
        (1234567, owner_id, *("",) * 7, "integer", *("text",) * 8),
    ]
