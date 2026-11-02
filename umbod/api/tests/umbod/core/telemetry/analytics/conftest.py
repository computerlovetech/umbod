from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
    DimensionGroup,
    InstanceScope,
    LogCountResult,
    LogWriteBatch,
    OwnedLog,
    PresentDimensionValue,
    UnownedLog,
    LogCountQuery,
    NoTimeBuckets,
    TelemetryAnalyticsReader,
    TimeRange,
)

from umbod.infrastructure import create_sqlite_analytics_runtime

from .in_memory import InMemoryTelemetryAnalyticsReader, NormalizedLog

ReaderFactory = Callable[[tuple[NormalizedLog, ...]], TelemetryAnalyticsReader]


class SeededSqliteReader:
    def __init__(self, path: Path, logs: tuple[NormalizedLog, ...]) -> None:
        self._runtime = create_sqlite_analytics_runtime(path, ())
        self._batch = LogWriteBatch(
            records=tuple(
                AnalyticsLogRecord(
                    occurred_at=log.occurred_at,
                    owner=UnownedLog(kind="unowned")
                    if log.owner_id is None
                    else OwnedLog(kind="owned", owner_id=log.owner_id),
                    dimensions=tuple(
                        DimensionGroup(
                            dimension=dimension,
                            value=PresentDimensionValue(kind="present", value=value),
                        )
                        for dimension, value in log.dimensions.items()
                    ),
                )
                for log in logs
            )
        )
        self._seeded = False

    async def count_logs(self, query: LogCountQuery) -> LogCountResult:
        if not self._seeded:
            await self._runtime.create_writer().append_logs(self._batch)
            self._seeded = True
        return await self._runtime.create_reader().count_logs(query)


@pytest.fixture(params=["in_memory", "sqlite"])
def reader_factory(request: pytest.FixtureRequest, tmp_path: Path) -> ReaderFactory:
    readers = []

    def create_reader(logs: tuple[NormalizedLog, ...]) -> TelemetryAnalyticsReader:
        if request.param == "in_memory":
            return InMemoryTelemetryAnalyticsReader(logs)
        reader = SeededSqliteReader(
            tmp_path / f"analytics-{len(readers)}.sqlite3", logs
        )
        readers.append(reader)
        return reader

    return create_reader


@pytest.fixture
def query() -> LogCountQuery:
    return LogCountQuery(
        scope=InstanceScope(kind="instance"),
        time_range=TimeRange(
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 1, 2, tzinfo=timezone.utc),
        ),
        filters=(),
        group_by=(),
        bucketing=NoTimeBuckets(kind="none"),
        max_groups=1000,
    )
