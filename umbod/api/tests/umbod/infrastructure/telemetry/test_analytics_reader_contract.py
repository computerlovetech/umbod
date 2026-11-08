from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
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
        pagination={"limit": 1000, "offset": 0},
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
    assert await reader.count_logs(_query(query, scope=scope)) == LogCountResult(has_more=False,
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
    assert await reader.count_logs(filtered) == LogCountResult(has_more=False, rows=(_row(2),))


@pytest.mark.asyncio
async def test_canonical_tool_union_excludes_skills_and_missing_enrichment(
    reader_factory: AsyncReaderFactory, query: LogCountQuery,
) -> None:
    reader = await reader_factory((
        _log(None, activity_kind="file_read", outcome="success"),
        _log(None, activity_kind="file_edit", outcome="failure"),
        _log(None, activity_kind="tool_call", outcome="unknown"),
        _log(None, activity_kind="skill_activation"),
        _log(None, event_name="unrecognized"),
    ))
    tool_filter = DimensionFilter(
        dimension=LogDimension.ACTIVITY_KIND, values=("tool_call", "file_read", "file_edit"),
    )
    result = await reader.count_logs(_query(query, filters=(tool_filter,)))
    assert result == LogCountResult(has_more=False, rows=(_row(3),))
    failures = await reader.count_logs(_query(query, filters=(
        tool_filter, DimensionFilter(dimension=LogDimension.OUTCOME, values=("failure",)),
    )))
    assert failures == LogCountResult(has_more=False, rows=(_row(1),))
    outcomes = await reader.count_logs(_query(query, group_by=(LogDimension.OUTCOME,)))
    assert outcomes == LogCountResult(has_more=False, rows=(
        _row(2, ((LogDimension.OUTCOME, None),)),
        _row(1, ((LogDimension.OUTCOME, "failure"),)),
        _row(1, ((LogDimension.OUTCOME, "success"),)),
        _row(1, ((LogDimension.OUTCOME, "unknown"),)),
    ))


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
    assert await reader.count_logs(grouped) == LogCountResult(has_more=False,
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
        assert await reader.count_logs(filtered) == LogCountResult(has_more=False,
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
    ) == LogCountResult(has_more=False, rows=expected)


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
    assert await reader.count_logs(selected) == LogCountResult(has_more=False,
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
        pagination={"limit": 5, "offset": 0},
    )
    assert await reader.count_logs(selected) == LogCountResult(has_more=False,
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

    page = await reader.count_logs(_query(selected, pagination={"limit": 4, "offset": 0}))
    full = await reader.count_logs(selected)
    assert page.rows == full.rows[:4]
    assert page.has_more is True


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
    assert await reader.count_logs(selected) == LogCountResult(has_more=False, rows=expected)


@pytest.mark.asyncio
async def test_exact_page_limit_succeeds_and_extra_group_sets_has_more(
    reader_factory: AsyncReaderFactory,
    query: LogCountQuery,
) -> None:
    reader = await reader_factory(
        (_log(None, source="b"), _log(None, source="a"), _log(None, source="a"))
    )
    selected = _query(query, group_by=(LogDimension.SOURCE,), pagination={"limit": 2, "offset": 0})
    assert await reader.count_logs(selected) == LogCountResult(has_more=False,
        rows=(
            _row(2, ((LogDimension.SOURCE, "a"),)),
            _row(1, ((LogDimension.SOURCE, "b"),)),
        )
    )
    page = await reader.count_logs(_query(selected, pagination={"limit": 1, "offset": 0}))
    assert page == LogCountResult(
        rows=(_row(2, ((LogDimension.SOURCE, "a"),)),), has_more=True
    )


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
        pagination={"limit": 1, "offset": 0},
    )
    assert await reader.count_logs(selected) == LogCountResult(has_more=False,
        rows=(_row(2, ((LogDimension.TOOL_NAME, "a"),)),)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [1, 2, 3, 1000])
async def test_pages_traverse_completed_aggregates_in_bucket_and_dimension_order(
    reader_factory: AsyncReaderFactory, query: LogCountQuery, limit: int,
) -> None:
    source = LogDimension.SOURCE
    logs = tuple(
        _log("keep", **dimensions).model_copy(update={"occurred_at": instant})
        for instant, dimensions in (
            (EPOCH + timedelta(hours=1), {"source": "a"}),
            (EPOCH, {"source": "z"}),
            (EPOCH, {"source": ""}),
            (EPOCH, {}),
            (EPOCH, {"source": ""}),
            (EPOCH + timedelta(hours=1), {}),
        )
    )
    reader = await reader_factory(logs + (
        _log("other", source="discard"),
        _log("keep", source="filtered", severity="DEBUG"),
        _log("keep", source="outside").model_copy(update={
            "occurred_at": query.time_range.end,
        }),
    ))
    selected = _query(
        query, scope=OwnersScope(kind="owners", owner_ids=("keep",)),
        filters=(DimensionFilter(dimension=source, values=("", "z", "a")),),
        group_by=(source,),
        bucketing=FixedTimeBuckets(kind="fixed", width=BucketWidth.HOUR),
    )
    expected = (
        _row(2, ((source, ""),), EPOCH),
        _row(1, ((source, "z"),), EPOCH),
        _row(1, ((source, "a"),), EPOCH + timedelta(hours=1)),
    )
    traversed: list[LogCountRow] = []
    for offset in range(0, len(expected), limit):
        page = await reader.count_logs(_query(
            selected, pagination={"limit": limit, "offset": offset},
        ))
        assert page.rows == expected[offset:offset + limit]
        assert page.has_more is (offset + limit < len(expected))
        traversed.extend(page.rows)
    assert tuple(traversed) == expected
    for offset in (len(expected), len(expected) + 1, 9007199254740991):
        assert await reader.count_logs(_query(
            selected, pagination={"limit": limit, "offset": offset},
        )) == LogCountResult(rows=(), has_more=False)
    unfiltered = _query(selected, filters=())
    expected_missing = (
        _row(1, ((source, None),), EPOCH),
        _row(2, ((source, ""),), EPOCH),
    )
    for offset, expected_row in enumerate(expected_missing):
        page = await reader.count_logs(_query(
            unfiltered, pagination={"limit": 1, "offset": offset},
        ))
        assert page.rows == (expected_row,)
        assert page.has_more is True


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_ungrouped_count_is_a_single_paginated_row(
    reader_factory: AsyncReaderFactory, query: LogCountQuery, empty: bool,
) -> None:
    reader = await reader_factory(() if empty else (_log(None), _log(None)))
    assert await reader.count_logs(_query(
        query, pagination={"limit": 1, "offset": 0},
    )) == LogCountResult(rows=(_row(0 if empty else 2),), has_more=False)
    assert await reader.count_logs(_query(
        query, pagination={"limit": 1, "offset": 1},
    )) == LogCountResult(rows=(), has_more=False)
