from datetime import datetime, timezone

import pytest

from umbod.core.telemetry.analytics import (
    InstanceScope,
    LogCountQuery,
    NoTimeBuckets,
    TimeRange,
)

from tests.support.telemetry_analytics import (
    InMemoryTelemetryAnalyticsReader,
    ReaderFactory,
)


@pytest.fixture
def reader_factory() -> ReaderFactory:
    return InMemoryTelemetryAnalyticsReader


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
        pagination={"limit": 1000, "offset": 0},
    )
