from datetime import datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError

import umbod.core.telemetry.analytics as analytics
from umbod.core.telemetry.analytics import (
    DimensionFilter,
    DimensionGroup,
    FixedTimeBuckets,
    InstanceScope,
    LogCountQuery,
    LogCountResult,
    LogCountRow,
    LogDimension,
    MissingDimensionValue,
    NoTimeBuckets,
    OwnersScope,
    PresentDimensionValue,
    TimeBucket,
    TimeRange,
    Unbucketed,
)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", {"kind": "unknown"}),
        ("scope", {"kind": "owners", "owner_ids": []}),
        ("scope", {"kind": "owners", "owner_ids": ["a", "a"]}),
        ("scope", {"kind": "owners", "owner_ids": [""]}),
        ("scope", {"kind": "owners", "owner_ids": ["  "]}),
        ("scope", {"kind": "owners", "owner_ids": [1]}),
        ("scope", {"kind": "owners"}),
        ("scope", {"kind": "instance", "owner_ids": ["a"]}),
        ("scope", {}),
        ("bucketing", {"kind": "fixed", "width": "week"}),
        ("bucketing", {"kind": "fixed"}),
        ("bucketing", {"kind": "unknown"}),
        ("bucketing", {"kind": "none", "width": "hour"}),
        ("max_groups", 0),
        ("max_groups", 1001),
        ("max_groups", True),
        ("max_groups", 1.5),
        ("max_groups", "1"),
        ("filters", [{"dimension": "invalid", "values": ["a"]}]),
        ("filters", [{"dimension": "source", "values": []}]),
        ("filters", [{"dimension": "source", "values": ["a", "a"]}]),
        ("filters", [{"dimension": "source", "values": [None]}]),
        ("filters", [{"dimension": "source", "values": [1]}]),
        ("filters", [{"dimension": "source"}]),
        ("filters", [
            {"dimension": "source", "values": ["a"]},
            {"dimension": "source", "values": ["b"]},
        ]),
        ("group_by", ["source", "source"]),
        ("group_by", ["invalid"]),
        ("unknown", "value"),
        ("time_range", {"start": "2025-01-01T00:00:00", "end": "2025-01-02T00:00:00Z"}),
        ("time_range", {"start": "2025-01-01T00:00:00Z", "end": "2025-01-02T00:00:00"}),
        ("time_range", {"start": "2025-01-01T00:00:00Z", "end": "2025-01-01T00:00:00Z"}),
        ("time_range", {"start": "2025-01-02T00:00:00Z", "end": "2025-01-01T00:00:00Z"}),
        ("time_range", {"start": "2025-01-01T01:00:00+01:00", "end": "2025-01-01T00:00:00Z"}),
    ],
)
def test_query_rejects_invalid_values(
    query: LogCountQuery, field: str, value: object
) -> None:
    payload = query.model_dump(mode="json") | {field: value}
    with pytest.raises(ValidationError):
        LogCountQuery.model_validate(payload)


@pytest.mark.parametrize("field", tuple(LogCountQuery.model_fields))
def test_every_query_field_is_explicitly_required(query: LogCountQuery, field: str) -> None:
    payload = query.model_dump(mode="json")
    del payload[field]
    with pytest.raises(ValidationError):
        LogCountQuery.model_validate(payload)


@pytest.mark.parametrize("max_groups", [1, 1000])
def test_query_accepts_group_limit_boundaries(query: LogCountQuery, max_groups: int) -> None:
    parsed = LogCountQuery.model_validate(query.model_dump() | {"max_groups": max_groups})
    assert parsed.max_groups == max_groups


def test_times_normalize_to_utc() -> None:
    start = datetime(2025, 1, 1, 5, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    period = TimeRange(start=start, end=start + timedelta(hours=1))
    bucket = TimeBucket(kind="bucket", start=start)
    expected = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert (period.start, period.end, bucket.start) == (
        expected, expected + timedelta(hours=1), expected
    )
    assert all(value.tzinfo is timezone.utc for value in (period.start, period.end, bucket.start))


MODEL_CASES: tuple[BaseModel, ...] = (
    InstanceScope(kind="instance"),
    OwnersScope(kind="owners", owner_ids=("a",)),
    TimeRange(
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2025, 1, 2, tzinfo=timezone.utc),
    ),
    DimensionFilter(dimension=LogDimension.SOURCE, values=("a",)),
    NoTimeBuckets(kind="none"),
    FixedTimeBuckets(kind="fixed", width="minute"),
    MissingDimensionValue(kind="missing"),
    PresentDimensionValue(kind="present", value=""),
    DimensionGroup(dimension=LogDimension.SOURCE, value=MissingDimensionValue(kind="missing")),
    Unbucketed(kind="none"),
    TimeBucket(kind="bucket", start=datetime(2025, 1, 1, tzinfo=timezone.utc)),
    LogCountRow(groups=(), count=0, bucket=Unbucketed(kind="none")),
    LogCountResult(rows=()),
)


@pytest.mark.parametrize("model", MODEL_CASES, ids=lambda model: type(model).__name__)
def test_all_models_forbid_extra_fields_and_are_frozen(model: BaseModel) -> None:
    with pytest.raises(ValidationError):
        type(model).model_validate(model.model_dump() | {"unknown": True})
    field = next(iter(type(model).model_fields))
    with pytest.raises(ValidationError):
        setattr(model, field, getattr(model, field))


def test_query_is_frozen_and_roundtrips_as_json(query: LogCountQuery) -> None:
    assert LogCountQuery.model_validate_json(query.model_dump_json()) == query
    with pytest.raises(ValidationError):
        query.max_groups = 2


@pytest.mark.parametrize(
    "payload",
    [
        {"groups": [], "count": -1, "bucket": {"kind": "none"}},
        {"groups": [], "count": True, "bucket": {"kind": "none"}},
        {"groups": [], "count": 1.2, "bucket": {"kind": "none"}},
        {"groups": [], "count": 0},
        {"groups": [], "count": 0, "bucket": None},
        {"groups": [], "count": 0, "bucket": {"kind": "invalid"}},
        {"groups": [], "count": 0, "bucket": {"kind": "bucket", "start": "2025-01-01T00:00:00"}},
        {"groups": [{"dimension": "source", "value": None}], "count": 0, "bucket": {"kind": "none"}},
        {"groups": [{"dimension": "source", "value": {"kind": "present"}}], "count": 0, "bucket": {"kind": "none"}},
        {"groups": [{"dimension": "source", "value": {"kind": "present", "value": 1}}], "count": 0, "bucket": {"kind": "none"}},
        {"groups": [{"dimension": "source", "value": {"kind": "missing", "value": ""}}], "count": 0, "bucket": {"kind": "none"}},
        {"groups": [{"dimension": "invalid", "value": {"kind": "missing"}}], "count": 0, "bucket": {"kind": "none"}},
    ],
)
def test_rows_reject_invalid_counts_buckets_and_dimension_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        LogCountRow.model_validate(payload)


def test_results_and_nested_collections_are_immutable_tuples() -> None:
    result = LogCountResult.model_validate({
        "rows": [{
            "groups": [{"dimension": "source", "value": {"kind": "present", "value": ""}}],
            "count": 1,
            "bucket": {"kind": "none"},
        }]
    })
    assert isinstance(result.rows, tuple)
    assert isinstance(result.rows[0].groups, tuple)
    assert LogCountResult.model_validate_json(result.model_dump_json()) == result


def test_public_exports_are_exact() -> None:
    expected = {
        "AnalyticsResultLimitExceeded", "BucketWidth", "DimensionFilter", "DimensionGroup",
        "FixedTimeBuckets", "InstanceScope", "LogCountQuery", "LogCountResult", "LogCountRow",
        "LogDimension", "MissingDimensionValue", "NoTimeBuckets", "OwnersScope",
        "PresentDimensionValue", "TelemetryAnalyticsReader", "TelemetryAnalyticsUnavailable",
        "TimeBucket", "TimeRange", "Unbucketed",
        "AnalyticsLogRecord", "LogWriteBatch", "OwnedLog", "UnownedLog",
        "TelemetryAnalyticsRuntime", "TelemetryAnalyticsWriter",
    }
    assert set(analytics.__all__) == expected
    assert all(getattr(analytics, name) is not None for name in expected)
