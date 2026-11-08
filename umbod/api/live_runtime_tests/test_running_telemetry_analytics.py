from uuid import uuid4

import httpx
import pytest
from pydantic import JsonValue

from conftest import RuntimeEndpoints


def test_running_canonical_activity_reports_preserve_raw_events(
    runtime_endpoints: RuntimeEndpoints, otlp_bearer_token: str,
) -> None:
    identifier = uuid4().hex
    claude_source = f"activity-claude-{identifier}"
    codex_source = f"activity-codex-{identifier}"
    session = f"activity-session-{identifier}"
    resource_logs = []
    for source, events in (
        (claude_source, (
            ("claude_code.tool_result", "Read", {"stringValue": "true"}, "ERROR"),
            ("claude_code.tool_result", "Edit", {"stringValue": "false"}, "INFO"),
        )),
        (codex_source, (
            ("codex.tool_result", "exec_command", {"boolValue": True}, "ERROR"),
            ("codex.tool_result", "apply_patch", {"boolValue": False}, "INFO"),
            ("codex.skill_invocation", "", {}, "INFO"),
        )),
    ):
        records = []
        for event, tool, success, severity in events:
            records.append({
                "timeUnixNano": "1767226200000000000",
                "eventName": event, "severityText": severity,
                "attributes": [
                    {"key": "conversation.id", "value": {"stringValue": session}},
                    {"key": "tool_name", "value": {"stringValue": tool}},
                    {"key": "success", "value": success},
                ],
            })
        resource_logs.append({
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": source}},
            ]},
            "scopeLogs": [{"logRecords": records}],
        })
    ingestion = httpx.post(
        f"{runtime_endpoints.otlp_base_url}/v1/logs",
        json={"resourceLogs": resource_logs},
        headers={"Authorization": f"Bearer {otlp_bearer_token}"}, timeout=10,
    )
    assert ingestion.status_code == 200, ingestion.text
    for filters, expected_counts in (
        ([{"dimension": "activity_kind", "values": ["tool_call", "file_read", "file_edit"]}], [(claude_source, 2), (codex_source, 2)]),
        ([{"dimension": "activity_kind", "values": ["file_read"]}], [(claude_source, 1)]),
        ([{"dimension": "activity_kind", "values": ["file_edit"]}], [(claude_source, 1), (codex_source, 1)]),
        ([{"dimension": "activity_kind", "values": ["skill_activation"]}], [(codex_source, 1)]),
        ([{"dimension": "activity_kind", "values": ["tool_call", "file_read", "file_edit"]},
          {"dimension": "outcome", "values": ["failure"]}], [(claude_source, 1), (codex_source, 1)]),
        ([{"dimension": "outcome", "values": ["success"]}], [(claude_source, 1), (codex_source, 1)]),
        ([{"dimension": "event_name", "values": ["claude_code.tool_result"]}], [(claude_source, 2)]),
        ([{"dimension": "event_name", "values": ["codex.tool_result"]}], [(codex_source, 2)]),
        ([{"dimension": "event_name", "values": ["codex.skill_invocation"]}], [(codex_source, 1)]),
        ([], [(claude_source, 2), (codex_source, 3)]),
    ):
        response = httpx.post(
            f"{runtime_endpoints.api_base_url}/api/admin/telemetry/log-counts",
            json={
                "time_range": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
                "filters": [{"dimension": "source", "values": [claude_source, codex_source]}, *filters],
                "group_by": ["source", "session_id"], "bucketing": {"kind": "none"},
                "pagination": {"limit": 100, "offset": 0},
            },
            headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}, timeout=10,
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"has_more": False, "rows": [
            {
                "groups": [
                    {"dimension": "source", "value": {"kind": "present", "value": source}},
                    {"dimension": "session_id", "value": {"kind": "present", "value": session}},
                ],
                "count": count, "bucket": {"kind": "none"},
            }
            for source, count in expected_counts
        ]}


@pytest.fixture
def analytics_source(runtime_endpoints: RuntimeEndpoints, otlp_bearer_token: str) -> str:
    source = f"analytics-runtime-{uuid4().hex}"
    payload = {"resourceLogs": [{
        "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": source}}]},
        "scopeLogs": [{"logRecords": [
            {"timeUnixNano": "1767226200000000000", "eventName": "tool_result", "severityText": "INFO",
             "attributes": [{"key": "tool.name", "value": {"stringValue": "shell"}}]},
            {"timeUnixNano": "1767226800000000000", "eventName": "tool_result", "severityText": "ERROR",
             "attributes": [{"key": "tool.name", "value": {"stringValue": ""}}]},
            {"timeUnixNano": "1767229800000000000", "eventName": "user_prompt"},
        ]}],
    }]}
    response = httpx.post(
        f"{runtime_endpoints.otlp_base_url}/v1/logs", json=payload,
        headers={"Authorization": f"Bearer {otlp_bearer_token}"}, timeout=10,
    )
    response.raise_for_status()
    return source


@pytest.mark.parametrize("group_by,filters,bucketing,expected", [
    ([], [], {"kind": "none"}, [{"groups": [], "count": 3, "bucket": {"kind": "none"}}]),
    (["event_name"], [], {"kind": "none"}, [
        {"groups": [{"dimension": "event_name", "value": {"kind": "present", "value": "tool_result"}}], "count": 2, "bucket": {"kind": "none"}},
        {"groups": [{"dimension": "event_name", "value": {"kind": "present", "value": "user_prompt"}}], "count": 1, "bucket": {"kind": "none"}},
    ]),
    (["tool_name"], [], {"kind": "none"}, [
        {"groups": [{"dimension": "tool_name", "value": {"kind": "missing"}}], "count": 1, "bucket": {"kind": "none"}},
        {"groups": [{"dimension": "tool_name", "value": {"kind": "present", "value": ""}}], "count": 1, "bucket": {"kind": "none"}},
        {"groups": [{"dimension": "tool_name", "value": {"kind": "present", "value": "shell"}}], "count": 1, "bucket": {"kind": "none"}},
    ]),
    ([], [{"dimension": "severity", "values": ["INFO", "ERROR"]}], {"kind": "none"}, [{"groups": [], "count": 2, "bucket": {"kind": "none"}}]),
    ([], [], {"kind": "fixed", "width": "hour"}, [
        {"groups": [], "count": 2, "bucket": {"kind": "bucket", "start": "2026-01-01T00:00:00Z"}},
        {"groups": [], "count": 1, "bucket": {"kind": "bucket", "start": "2026-01-01T01:00:00Z"}},
    ]),
])
@pytest.mark.parametrize("limit", [1, 100])
def test_running_analytics_reads_exports_in_multiple_aggregate_views(
    runtime_endpoints: RuntimeEndpoints,
    analytics_source: str,
    group_by: list[str],
    filters: list[dict[str, JsonValue]],
    bucketing: dict[str, str],
    expected: list[dict[str, JsonValue]],
    limit: int,
) -> None:
    for offset in range(0, len(expected), limit):
        response = httpx.post(
            f"{runtime_endpoints.api_base_url}/api/admin/telemetry/log-counts",
            json={
                "time_range": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
                "filters": [{"dimension": "source", "values": [analytics_source]}, *filters],
                "group_by": group_by, "bucketing": bucketing, "pagination": {"limit": limit, "offset": offset},
            },
            headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}, timeout=10,
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "has_more": offset + limit < len(expected), "rows": expected[offset:offset + limit],
        }
