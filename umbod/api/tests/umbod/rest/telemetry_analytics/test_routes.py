from datetime import datetime, timezone

import pytest

from umbod.core.telemetry.analytics import (
    AnalyticsResultLimitExceeded,
    InstanceScope,
    LogCountQuery,
    LogCountResult,
    TelemetryAnalyticsReader,
    TelemetryAnalyticsUnavailable,
)
from umbod.rest.telemetry.dependencies import get_analytics_reader

from .conftest import AnalyticsHttp

BASE = "/api/admin/telemetry/log-counts"


def test_instance_count_includes_owned_and_unowned_logs(
    analytics_http: AnalyticsHttp, query_body: dict[str, object],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body)
    assert response.status_code == 200
    assert response.json() == {"rows": [{"groups": [], "count": 3, "bucket": {"kind": "none"}}]}
    assert analytics_http.reader.queries[0].scope == InstanceScope(kind="instance")
    assert response.headers["cache-control"] == "no-store"


def test_counts_preserve_requested_grouping_order_and_missing_values(
    analytics_http: AnalyticsHttp, query_body: dict[str, object],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body | {"group_by": ["tool_name", "source"]})
    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [row["groups"][0]["value"] for row in rows] == [
        {"kind": "missing"}, {"kind": "present", "value": ""}, {"kind": "present", "value": "shell"},
    ]
    assert all([group["dimension"] for group in row["groups"]] == ["tool_name", "source"] for row in rows)


def test_filters_use_or_within_values_and_and_across_dimensions(
    analytics_http: AnalyticsHttp, query_body: dict[str, object],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body | {"filters": [
        {"dimension": "source", "values": ["codex", "claude-code"]},
        {"dimension": "severity", "values": ["ERROR"]},
    ]})
    assert response.status_code == 200
    assert response.json()["rows"][0]["count"] == 1


def test_exact_empty_string_filter_does_not_match_missing_values(
    analytics_http: AnalyticsHttp, query_body: dict[str, object],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body | {"filters": [{"dimension": "tool_name", "values": [""]}]})
    assert response.status_code == 200
    assert response.json()["rows"][0]["count"] == 1


def test_time_range_is_half_open_and_normalized_to_utc(
    analytics_http: AnalyticsHttp, query_body: dict[str, object],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body | {
        "time_range": {"start": "2026-01-01T01:10:00+01:00", "end": "2026-01-01T01:20:00+01:00"},
    })
    assert response.status_code == 200
    assert response.json()["rows"][0]["count"] == 1
    assert analytics_http.reader.queries[0].time_range.start == datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc)


def test_hourly_buckets_only_return_observed_intervals(
    analytics_http: AnalyticsHttp, query_body: dict[str, object],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body | {"bucketing": {"kind": "fixed", "width": "hour"}})
    assert response.status_code == 200
    assert response.json() == {"rows": [
        {"groups": [], "count": 2, "bucket": {"kind": "bucket", "start": "2026-01-01T00:00:00Z"}},
        {"groups": [], "count": 1, "bucket": {"kind": "bucket", "start": "2026-01-01T01:00:00Z"}},
    ]}


@pytest.mark.parametrize("group_by,expected", [([], [{"groups": [], "count": 0, "bucket": {"kind": "none"}}]), (["source"], [])])
def test_no_matches_have_explicit_zero_or_empty_groups(
    analytics_http: AnalyticsHttp, query_body: dict[str, object], group_by: list[str], expected: list[dict[str, object]],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body | {
        "filters": [{"dimension": "source", "values": ["not-ingested"]}], "group_by": group_by,
    })
    assert response.status_code == 200
    assert response.json() == {"rows": expected}


@pytest.mark.parametrize("patch", [
    {"scope": {"kind": "instance"}},
    {"scope": {"kind": "owners", "owner_ids": ["member"]}},
    {"group_by": ["source", "source"]},
    {"group_by": ["unknown"]},
    {"filters": [{"dimension": "source", "values": []}]},
    {"filters": [{"dimension": "source", "values": ["codex", "codex"]}]},
    {"filters": [{"dimension": "source", "values": ["codex"]}, {"dimension": "source", "values": ["claude-code"]}]},
    {"filters": [{"dimension": "severity", "values": [42]}]},
    {"max_groups": 0}, {"max_groups": 1001}, {"max_groups": True}, {"max_groups": "100"},
    {"bucketing": {"kind": "fixed", "width": "week"}},
    {"bucketing": {"kind": "none", "width": "hour"}},
    {"time_range": {"start": "2026-01-01T00:00:00", "end": "2026-01-02T00:00:00Z"}},
    {"time_range": {"start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"}},
])
def test_invalid_queries_are_rejected_before_reading(
    analytics_http: AnalyticsHttp, query_body: dict[str, object], patch: dict[str, object],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body | patch)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert analytics_http.reader.queries == []


def test_result_limit_error_does_not_return_partial_counts(
    analytics_http: AnalyticsHttp, query_body: dict[str, object],
) -> None:
    response = analytics_http.client.post(BASE, json=query_body | {"group_by": ["source"], "max_groups": 1})
    assert response.status_code == 422
    assert "Too many result groups" in response.json()["detail"]
    assert "rows" not in response.json()
    assert response.headers["cache-control"] == "no-store"


class FailingReader:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def count_logs(self, query: LogCountQuery) -> LogCountResult:
        raise self.error


@pytest.mark.parametrize("failure,status", [
    (TelemetryAnalyticsUnavailable("private database path"), 503),
    (AnalyticsResultLimitExceeded("private SQL diagnostic"), 422),
    (RuntimeError("private implementation diagnostic"), 500),
])
def test_backend_failures_do_not_expose_diagnostics_or_fabricate_zeroes(
    analytics_http: AnalyticsHttp, query_body: dict[str, object], failure: Exception, status: int,
) -> None:
    def provide_reader() -> TelemetryAnalyticsReader:
        return FailingReader(failure)

    analytics_http.admin.dependency_overrides[get_analytics_reader] = provide_reader
    response = analytics_http.client.post(BASE, json=query_body)
    assert response.status_code == status
    assert "private" not in response.text
    assert "rows" not in response.text
