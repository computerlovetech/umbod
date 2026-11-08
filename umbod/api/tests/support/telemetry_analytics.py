from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict

from umbod.core.telemetry.analytics import (
    BucketWidth,
    DimensionGroup,
    FixedTimeBuckets,
    LogCountQuery,
    LogCountResult,
    LogCountRow,
    LogDimension,
    MissingDimensionValue,
    OwnersScope,
    PresentDimensionValue,
    TelemetryAnalyticsReader,
    TimeBucket,
    Unbucketed,
)
from umbod.core.telemetry.analytics.models import UtcDatetime


class NormalizedLog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    occurred_at: UtcDatetime
    owner_id: Optional[str]
    dimensions: dict[LogDimension, str]


class InMemoryTelemetryAnalyticsReader:
    def __init__(self, logs: tuple[NormalizedLog, ...]) -> None:
        self._logs = tuple(log.model_copy(deep=True) for log in logs)

    async def count_logs(self, query: LogCountQuery) -> LogCountResult:
        counts: Counter[
            tuple[Unbucketed | TimeBucket, tuple[DimensionGroup, ...]]
        ] = Counter()
        if not query.group_by and not isinstance(query.bucketing, FixedTimeBuckets):
            counts[(Unbucketed(kind="none"), ())] = 0
        for log in self._logs:
            if not self._matches(log, query):
                continue
            groups = tuple(
                DimensionGroup(
                    dimension=dimension,
                    value=(
                        PresentDimensionValue(
                            kind="present", value=log.dimensions[dimension]
                        )
                        if dimension in log.dimensions
                        else MissingDimensionValue(kind="missing")
                    ),
                )
                for dimension in query.group_by
            )
            counts[(self._bucket(log.occurred_at, query), groups)] += 1
        rows = tuple(
            LogCountRow(bucket=bucket, groups=groups, count=count)
            for (bucket, groups), count in counts.items()
        )
        ordered = tuple(sorted(rows, key=self._sort_key))
        start = query.pagination.offset
        end = start + query.pagination.limit
        return LogCountResult(rows=ordered[start:end], has_more=len(ordered) > end)

    @staticmethod
    def _matches(log: NormalizedLog, query: LogCountQuery) -> bool:
        if not query.time_range.start <= log.occurred_at < query.time_range.end:
            return False
        if isinstance(query.scope, OwnersScope) and log.owner_id not in query.scope.owner_ids:
            return False
        return all(
            item.dimension in log.dimensions
            and log.dimensions[item.dimension] in item.values
            for item in query.filters
        )

    @staticmethod
    def _bucket(
        occurred_at: datetime, query: LogCountQuery
    ) -> Unbucketed | TimeBucket:
        if not isinstance(query.bucketing, FixedTimeBuckets):
            return Unbucketed(kind="none")
        seconds = {
            BucketWidth.MINUTE: 60,
            BucketWidth.HOUR: 3600,
            BucketWidth.DAY: 86400,
        }[query.bucketing.width]
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        width = timedelta(seconds=seconds)
        start = epoch + ((occurred_at - epoch) // width) * width
        return TimeBucket(kind="bucket", start=start)

    @staticmethod
    def _sort_key(row: LogCountRow) -> tuple[datetime, tuple[tuple[int, str], ...]]:
        start = (
            row.bucket.start
            if isinstance(row.bucket, TimeBucket)
            else datetime(1970, 1, 1, tzinfo=timezone.utc)
        )
        values = tuple(
            (1, group.value.value)
            if isinstance(group.value, PresentDimensionValue)
            else (0, "")
            for group in row.groups
        )
        return start, values


ReaderFactory = Callable[[tuple[NormalizedLog, ...]], TelemetryAnalyticsReader]
