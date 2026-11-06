from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
    AnalyticsResultLimitExceeded,
    BucketWidth,
    DimensionFilter,
    DimensionGroup,
    FixedTimeBuckets,
    InstanceScope,
    LogCountQuery,
    LogCountResult,
    LogCountRow,
    LogDimension,
    LogWriteBatch,
    MissingDimensionValue,
    NoTimeBuckets,
    OwnedLog,
    OwnersScope,
    PresentDimensionValue,
    TelemetryAnalyticsReader,
    TimeBucket,
    TimeRange,
    Unbucketed,
    UnownedLog,
)
from umbod.infrastructure import create_sqlite_analytics_runtime

from tests.support.telemetry_analytics import (
    InMemoryTelemetryAnalyticsReader,
    NormalizedLog,
)

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
AsyncReaderFactory = Callable[
    [tuple[NormalizedLog, ...]], Awaitable[TelemetryAnalyticsReader]
]


@pytest_asyncio.fixture(params=["in_memory", "sqlite"])
async def reader_factory(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[AsyncReaderFactory]:
    async with AsyncExitStack() as cleanup:
        runtime_count = 0

        async def create_reader(
            logs: tuple[NormalizedLog, ...],
        ) -> TelemetryAnalyticsReader:
            nonlocal runtime_count
            if request.param == "in_memory":
                return InMemoryTelemetryAnalyticsReader(logs)
            runtime = create_sqlite_analytics_runtime(
                tmp_path / f"analytics-{runtime_count}.sqlite3", ()
            )
            runtime_count += 1
            cleanup.push_async_callback(runtime.shutdown)
            await runtime.create_writer().append_logs(
                LogWriteBatch(
                    records=tuple(
                        AnalyticsLogRecord(
                            occurred_at=log.occurred_at,
                            owner=UnownedLog(kind="unowned")
                            if log.owner_id is None
                            else OwnedLog(kind="owned", owner_id=log.owner_id),
                            dimensions=tuple(
                                DimensionGroup(
                                    dimension=dimension,
                                    value=PresentDimensionValue(
                                        kind="present", value=value
                                    ),
                                )
                                for dimension, value in log.dimensions.items()
                            ),
                        )
                        for log in logs
                    )
                )
            )
            return runtime.create_reader()

        yield create_reader


@pytest.fixture
def query() -> LogCountQuery:
    return LogCountQuery(
        scope=InstanceScope(kind="instance"),
        time_range=TimeRange(
            start=EPOCH - timedelta(days=3), end=EPOCH + timedelta(days=3)
        ),
        filters=(),
        group_by=(),
        bucketing=NoTimeBuckets(kind="none"),
        max_groups=1000,
    )


def _log(owner: Optional[str], **dimensions: str) -> NormalizedLog:
    return NormalizedLog(
        occurred_at=EPOCH,
        owner_id=owner,
        dimensions={LogDimension(key): value for key, value in dimensions.items()},
    )


def _query(query: LogCountQuery, **changes: object) -> LogCountQuery:
    return LogCountQuery.model_validate(query.model_dump() | changes)


def _row(
    count: int,
    dimensions: tuple[tuple[LogDimension, Optional[str]], ...] = (),
    bucket: Optional[datetime] = None,
) -> LogCountRow:
    return LogCountRow(
        count=count,
        groups=tuple(
            DimensionGroup(
                dimension=dimension,
                value=MissingDimensionValue(kind="missing")
                if value is None
                else PresentDimensionValue(kind="present", value=value),
            )
            for dimension, value in dimensions
        ),
        bucket=Unbucketed(kind="none")
        if bucket is None
        else TimeBucket(kind="bucket", start=bucket),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owners,expected",
    [
        ((), 5),
        (("owner",), 2),
        (("Owner",), 1),
        (("owner", "other"), 3),
        (("absent",), 0),
    ],
)
async def test_owner_selection_excludes_null_and_preserves_case(
    reader_factory: AsyncReaderFactory,
    query: LogCountQuery,
    owners: tuple[str, ...],
    expected: int,
) -> None:
    reader = await reader_factory(
        tuple(_log(owner) for owner in (None, "owner", "owner", "Owner", "other"))
    )
    scope = (
        OwnersScope(kind="owners", owner_ids=owners)
        if owners
        else InstanceScope(kind="instance")
    )
    assert await reader.count_logs(_query(query, scope=scope)) == LogCountResult(
        rows=(_row(expected),)
    )


@pytest.mark.asyncio
async def test_filters_combine_or_values_and_dimensions_with_binary_exactness(
    reader_factory: AsyncReaderFactory,
    query: LogCountQuery,
) -> None:
    reader = await reader_factory(
        tuple(
            _log(None, **dimensions)
            for dimensions in (
                {"source": "api", "severity": "error"},
                {"source": "mcp", "severity": "error"},
                {"source": "API", "severity": "error"},
                {"source": "api ", "severity": "error"},
                {"source": "api", "severity": "Error"},
                {"source": "api"},
                {"severity": "error"},
            )
        )
    )
    filtered = _query(
        query,
        filters=(
            DimensionFilter(dimension=LogDimension.SOURCE, values=("api", "mcp")),
            DimensionFilter(dimension=LogDimension.SEVERITY, values=("error",)),
        ),
    )
    assert await reader.count_logs(filtered) == LogCountResult(rows=(_row(2),))


@pytest.mark.asyncio
@pytest.mark.parametrize("dimension", list(LogDimension))
async def test_writer_column_mapping_preserves_missing_empty_and_present_values(
    reader_factory: AsyncReaderFactory,
    query: LogCountQuery,
    dimension: LogDimension,
) -> None:
    records = []
    for value in (None, "", "value", "value"):
        dimensions = {
            item.value: f"distractor-{item.value}"
            for item in LogDimension
            if item != dimension
        }
        if value is not None:
            dimensions[dimension.value] = value
        records.append(_log(None, **dimensions))
    reader = await reader_factory(tuple(records))
    grouped = _query(query, group_by=(dimension,))
    assert await reader.count_logs(grouped) == LogCountResult(
        rows=(
            _row(1, ((dimension, None),)),
            _row(1, ((dimension, ""),)),
            _row(2, ((dimension, "value"),)),
        )
    )
    for value, count in (("", 1), ("value", 2)):
        filtered = _query(
            grouped, filters=(DimensionFilter(dimension=dimension, values=(value,)),)
        )
        assert await reader.count_logs(filtered) == LogCountResult(
            rows=(_row(count, ((dimension, value),)),)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("reverse", [False, True])
async def test_multidimension_rows_decode_in_query_order(
    reader_factory: AsyncReaderFactory,
    query: LogCountQuery,
    reverse: bool,
) -> None:
    reader = await reader_factory(
        (
            _log(None, source="a", tool_name="z"),
            _log(None, source="z", tool_name="a"),
            _log(None, source="a", tool_name="z"),
            _log(None, tool_name=""),
        )
    )
    source, tool = LogDimension.SOURCE, LogDimension.TOOL_NAME
    dimensions = (tool, source) if reverse else (source, tool)
    expected = (
        (
            _row(1, ((tool, ""), (source, None))),
            _row(1, ((tool, "a"), (source, "z"))),
            _row(2, ((tool, "z"), (source, "a"))),
        )
        if reverse
        else (
            _row(1, ((source, None), (tool, ""))),
            _row(2, ((source, "a"), (tool, "z"))),
            _row(1, ((source, "z"), (tool, "a"))),
        )
    )
    assert await reader.count_logs(
        _query(query, group_by=dimensions)
    ) == LogCountResult(rows=expected)


@pytest.mark.asyncio
async def test_microsecond_range_includes_start_and_excludes_end(
    reader_factory: AsyncReaderFactory,
    query: LogCountQuery,
) -> None:
    start = EPOCH + timedelta(microseconds=5)
    end = start + timedelta(microseconds=2)
    reader = await reader_factory(
        tuple(
            _log(None, source=label).model_copy(update={"occurred_at": instant})
            for instant, label in (
                (start - timedelta(microseconds=1), "before"),
                (start, "start"),
                (end - timedelta(microseconds=1), "inside"),
                (end, "end"),
            )
        )
    )
    selected = _query(
        query,
        time_range=TimeRange(start=start, end=end),
        group_by=(LogDimension.SOURCE,),
    )
    assert await reader.count_logs(selected) == LogCountResult(
        rows=(
            _row(1, ((LogDimension.SOURCE, "inside"),)),
            _row(1, ((LogDimension.SOURCE, "start"),)),
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "width,seconds",
    [(BucketWidth.MINUTE, 60), (BucketWidth.HOUR, 3600), (BucketWidth.DAY, 86400)],
)
async def test_epoch_floor_and_bucket_first_order_for_timezone_inputs(
    reader_factory: AsyncReaderFactory,
    query: LogCountQuery,
    width: BucketWidth,
    seconds: int,
) -> None:
    offset = timezone(timedelta(hours=5, minutes=30))
    reader = await reader_factory(
        tuple(
            NormalizedLog(
                occurred_at=instant.astimezone(offset),
                owner_id=None,
                dimensions={LogDimension.SOURCE: value},
            )
            for instant, value in (
                (EPOCH + timedelta(seconds=seconds), "a"),
                (EPOCH - timedelta(microseconds=1), "z"),
                (EPOCH, "z"),
                (EPOCH - timedelta(seconds=seconds, microseconds=1), "z"),
                (EPOCH + timedelta(seconds=seconds, microseconds=-1), "a"),
            )
        )
    )
    selected = _query(
        query,
        group_by=(LogDimension.SOURCE,),
        bucketing=FixedTimeBuckets(kind="fixed", width=width),
        max_groups=5,
    )
    assert await reader.count_logs(selected) == LogCountResult(
        rows=tuple(
            _row(1, ((LogDimension.SOURCE, value),), instant)
            for instant, value in (
                (EPOCH - timedelta(seconds=2 * seconds), "z"),
                (EPOCH - timedelta(seconds=seconds), "z"),
                (EPOCH, "a"),
                (EPOCH, "z"),
                (EPOCH + timedelta(seconds=seconds), "a"),
            )
        )
    )

    with pytest.raises(AnalyticsResultLimitExceeded):
        await reader.count_logs(_query(selected, max_groups=4))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "grouped,bucketed", [(False, False), (True, False), (False, True), (True, True)]
)
async def test_empty_aggregation_has_only_an_unbucketed_total_row(
    reader_factory: AsyncReaderFactory,
    query: LogCountQuery,
    grouped: bool,
    bucketed: bool,
) -> None:
    reader = await reader_factory(())
    selected = _query(
        query,
        group_by=(LogDimension.SOURCE,) if grouped else (),
        bucketing=FixedTimeBuckets(kind="fixed", width=BucketWidth.HOUR)
        if bucketed
        else query.bucketing,
    )
    expected = () if grouped or bucketed else (_row(0),)
    assert await reader.count_logs(selected) == LogCountResult(rows=expected)


@pytest.mark.asyncio
async def test_exact_group_limit_succeeds_and_one_extra_group_overflows(
    reader_factory: AsyncReaderFactory,
    query: LogCountQuery,
) -> None:
    reader = await reader_factory(
        (_log(None, source="b"), _log(None, source="a"), _log(None, source="a"))
    )
    selected = _query(query, group_by=(LogDimension.SOURCE,), max_groups=2)
    assert await reader.count_logs(selected) == LogCountResult(
        rows=(
            _row(2, ((LogDimension.SOURCE, "a"),)),
            _row(1, ((LogDimension.SOURCE, "b"),)),
        )
    )
    with pytest.raises(AnalyticsResultLimitExceeded):
        await reader.count_logs(_query(selected, max_groups=1))


@pytest.mark.asyncio
async def test_scope_and_filters_eliminate_groups_before_limit(
    reader_factory: AsyncReaderFactory,
    query: LogCountQuery,
) -> None:
    reader = await reader_factory(
        (
            _log("keep", source="keep", tool_name="a"),
            _log("keep", source="keep", tool_name="a"),
            _log("other", source="keep", tool_name="b"),
            _log(None, source="keep", tool_name="c"),
            _log("keep", source="discard", tool_name="d"),
        )
    )
    selected = _query(
        query,
        scope=OwnersScope(kind="owners", owner_ids=("keep",)),
        filters=(DimensionFilter(dimension=LogDimension.SOURCE, values=("keep",)),),
        group_by=(LogDimension.TOOL_NAME,),
        max_groups=1,
    )
    assert await reader.count_logs(selected) == LogCountResult(
        rows=(_row(2, ((LogDimension.TOOL_NAME, "a"),)),)
    )
