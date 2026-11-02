from datetime import datetime, timedelta, timezone

import pytest

from umbod.core.telemetry.analytics import (
    AnalyticsResultLimitExceeded,
    BucketWidth,
    DimensionFilter,
    DimensionGroup,
    FixedTimeBuckets,
    LogCountQuery,
    LogCountResult,
    LogCountRow,
    LogDimension,
    MissingDimensionValue,
    OwnersScope,
    PresentDimensionValue,
    TimeBucket,
    TimeRange,
    Unbucketed,
)

from .conftest import ReaderFactory
from .in_memory import NormalizedLog


def _query(query: LogCountQuery, **changes: object) -> LogCountQuery:
    return LogCountQuery.model_validate(query.model_dump() | changes)


def _log(
    occurred_at: datetime, owner: str | None, dimensions: dict[LogDimension, str]
) -> NormalizedLog:
    return NormalizedLog(occurred_at=occurred_at, owner_id=owner, dimensions=dimensions)


@pytest.mark.asyncio
async def test_empty_total_is_single_zero(
    reader_factory: ReaderFactory, query: LogCountQuery
) -> None:
    result = await reader_factory(()).count_logs(query)
    assert result == LogCountResult(
        rows=(LogCountRow(groups=(), count=0, bucket=Unbucketed(kind="none")),)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("grouped,bucketed", [(True, False), (False, True), (True, True)])
async def test_empty_grouped_or_bucketed_query_has_no_rows(
    reader_factory: ReaderFactory, query: LogCountQuery, grouped: bool, bucketed: bool
) -> None:
    query = _query(
        query,
        group_by=(LogDimension.SOURCE,) if grouped else (),
        bucketing=FixedTimeBuckets(kind="fixed", width=BucketWidth.HOUR)
        if bucketed
        else query.bucketing,
    )
    assert (await reader_factory(()).count_logs(query)).rows == ()


@pytest.mark.asyncio
async def test_time_range_is_start_inclusive_end_exclusive(
    reader_factory: ReaderFactory, query: LogCountQuery
) -> None:
    start, end = query.time_range.start, query.time_range.end
    logs = tuple(
        _log(instant, None, {})
        for instant in (
            start - timedelta(microseconds=1),
            start,
            end - timedelta(microseconds=1),
            end,
        )
    )
    assert (await reader_factory(logs).count_logs(query)).rows[0].count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope,expected",
    [
        ({"kind": "instance"}, 4),
        ({"kind": "owners", "owner_ids": ["a"]}, 2),
        ({"kind": "owners", "owner_ids": ["a", "b"]}, 3),
        ({"kind": "owners", "owner_ids": ["absent"]}, 0),
    ],
)
async def test_scope_controls_ownerless_and_owned_logs(
    reader_factory: ReaderFactory,
    query: LogCountQuery,
    scope: dict[str, object],
    expected: int,
) -> None:
    logs = tuple(_log(query.time_range.start, owner, {}) for owner in ("a", "a", "b", None))
    result = await reader_factory(logs).count_logs(_query(query, scope=scope))
    assert result.rows[0].count == expected


@pytest.mark.asyncio
async def test_filters_are_exact_or_within_dimension_and_across_dimensions(
    reader_factory: ReaderFactory, query: LogCountQuery
) -> None:
    logs = tuple(
        _log(query.time_range.start, "a", dimensions)
        for dimensions in (
            {LogDimension.SOURCE: "api", LogDimension.SEVERITY: "error"},
            {LogDimension.SOURCE: "mcp", LogDimension.SEVERITY: "error"},
            {LogDimension.SOURCE: "API", LogDimension.SEVERITY: "error"},
            {LogDimension.SOURCE: "api", LogDimension.SEVERITY: "info"},
            {LogDimension.SOURCE: "api"},
            {LogDimension.SEVERITY: "error"},
        )
    )
    query = _query(
        query,
        filters=(
            DimensionFilter(dimension=LogDimension.SOURCE, values=("api", "mcp")),
            DimensionFilter(dimension=LogDimension.SEVERITY, values=("error",)),
        ),
    )
    assert (await reader_factory(logs).count_logs(query)).rows[0].count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("dimension", list(LogDimension))
async def test_every_dimension_supports_exact_filtering(
    reader_factory: ReaderFactory, query: LogCountQuery, dimension: LogDimension
) -> None:
    logs = tuple(
        _log(query.time_range.start, None, values)
        for values in ({dimension: ""}, {dimension: "value"}, {})
    )
    query = _query(query, filters=(DimensionFilter(dimension=dimension, values=("",)),))
    assert (await reader_factory(logs).count_logs(query)).rows[0].count == 1


@pytest.mark.asyncio
async def test_group_order_preserves_query_dimensions_and_distinguishes_missing(
    reader_factory: ReaderFactory, query: LogCountQuery
) -> None:
    logs = tuple(
        _log(query.time_range.start, None, dimensions)
        for dimensions in (
            {LogDimension.SOURCE: "z", LogDimension.TOOL_NAME: "tool"},
            {LogDimension.SOURCE: ""},
            {},
            {LogDimension.SOURCE: "a"},
            {LogDimension.SOURCE: "a"},
        )
    )
    query = _query(query, group_by=(LogDimension.SOURCE, LogDimension.TOOL_NAME))
    result = await reader_factory(logs).count_logs(query)
    missing = MissingDimensionValue(kind="missing")
    expected = (
        (missing, missing, 1),
        (PresentDimensionValue(kind="present", value=""), missing, 1),
        (PresentDimensionValue(kind="present", value="a"), missing, 2),
        (
            PresentDimensionValue(kind="present", value="z"),
            PresentDimensionValue(kind="present", value="tool"),
            1,
        ),
    )
    assert result.rows == tuple(
        LogCountRow(
            groups=(
                DimensionGroup(dimension=LogDimension.SOURCE, value=source),
                DimensionGroup(dimension=LogDimension.TOOL_NAME, value=tool),
            ),
            count=count,
            bucket=Unbucketed(kind="none"),
        )
        for source, tool, count in expected
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "width,seconds", [(BucketWidth.MINUTE, 60), (BucketWidth.HOUR, 3600), (BucketWidth.DAY, 86400)]
)
async def test_fixed_buckets_are_utc_epoch_aligned_with_observed_rows_only(
    reader_factory: ReaderFactory,
    query: LogCountQuery,
    width: BucketWidth,
    seconds: int,
) -> None:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    start = epoch - timedelta(seconds=seconds)
    boundary = epoch + timedelta(seconds=seconds)
    logs = tuple(
        _log(instant.astimezone(timezone(timedelta(hours=5, minutes=30))), None, {})
        for instant in (
            boundary,
            epoch - timedelta(microseconds=1),
            epoch,
            boundary - timedelta(microseconds=1),
        )
    )
    query = _query(
        query,
        time_range=TimeRange(start=start, end=boundary + timedelta(seconds=seconds)),
        bucketing=FixedTimeBuckets(kind="fixed", width=width),
    )
    result = await reader_factory(logs).count_logs(query)
    assert result.rows == tuple(
        LogCountRow(groups=(), count=count, bucket=TimeBucket(kind="bucket", start=instant))
        for instant, count in ((start, 1), (epoch, 2), (boundary, 1))
    )


@pytest.mark.asyncio
async def test_buckets_sort_before_dimensions_and_limit_counts_rows(
    reader_factory: ReaderFactory, query: LogCountQuery
) -> None:
    start = query.time_range.start
    logs = tuple(
        _log(instant, "a", {LogDimension.SOURCE: source})
        for instant, source in (
            (start + timedelta(hours=1), "a"),
            (start, "z"),
            (start, "a"),
        )
    )
    query = _query(
        query,
        group_by=(LogDimension.SOURCE,),
        bucketing=FixedTimeBuckets(kind="fixed", width=BucketWidth.HOUR),
        max_groups=3,
    )
    reader = reader_factory(logs)
    result = await reader.count_logs(query)
    assert tuple(
        (row.bucket, row.groups[0].value) for row in result.rows
    ) == (
        (TimeBucket(kind="bucket", start=start), PresentDimensionValue(kind="present", value="a")),
        (TimeBucket(kind="bucket", start=start), PresentDimensionValue(kind="present", value="z")),
        (
            TimeBucket(kind="bucket", start=start + timedelta(hours=1)),
            PresentDimensionValue(kind="present", value="a"),
        ),
    )
    with pytest.raises(AnalyticsResultLimitExceeded):
        await reader.count_logs(_query(query, max_groups=2))


@pytest.mark.asyncio
async def test_scope_and_filters_apply_before_aggregation_limit(
    reader_factory: ReaderFactory, query: LogCountQuery
) -> None:
    logs = tuple(
        _log(query.time_range.start, owner, {LogDimension.SOURCE: source})
        for owner, source in (("a", "keep"), ("b", "other"), ("a", "excluded"))
    )
    query = _query(
        query,
        scope=OwnersScope(kind="owners", owner_ids=("a",)),
        filters=(DimensionFilter(dimension=LogDimension.SOURCE, values=("keep",)),),
        group_by=(LogDimension.SOURCE,),
        max_groups=1,
    )
    result = await reader_factory(logs).count_logs(query)
    assert tuple(row.count for row in result.rows) == (1,)


@pytest.mark.asyncio
async def test_repeated_calls_do_not_accumulate_counts(
    reader_factory: ReaderFactory, query: LogCountQuery
) -> None:
    reader = reader_factory((_log(query.time_range.start, None, {}),))
    first = await reader.count_logs(query)
    assert await reader.count_logs(query) == first
