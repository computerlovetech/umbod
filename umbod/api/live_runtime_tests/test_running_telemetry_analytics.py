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
                "eventName": (
                    "event otel/src/events/session_telemetry.rs:375"
                    if tool == "exec_command" else event
                ), "severityText": severity,
                "attributes": [
                    {"key": "event.name", "value": {"stringValue": event}},
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
        ([{"dimension": "event_name", "values": ["codex.tool_result"]}], [(codex_source, 1)]),
        ([{"dimension": "event_name", "values": ["event otel/src/events/session_telemetry.rs:375"]}], [(codex_source, 1)]),
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


def test_running_model_usage_and_estimated_cost_logs_do_not_become_tool_activity(
    runtime_endpoints: RuntimeEndpoints, otlp_bearer_token: str,
) -> None:
    source = f"model-usage-{uuid4().hex}"
    records = []
    for event, attributes in (
        ("claude_code.api_request", (
            ("model", {"stringValue": "claude-sonnet-4-6"}),
            ("input_tokens", {"intValue": "100"}),
            ("output_tokens", {"intValue": "20"}),
            ("cache_read_tokens", {"intValue": "30"}),
            ("cache_creation_tokens", {"intValue": "40"}),
            ("cost_usd_micros", {"intValue": "2500"}),
        )),
        ("claude_code.api_error", (
            ("attempt", {"intValue": "2"}),
            ("status_code", {"intValue": "429"}),
            ("duration_ms", {"stringValue": "NaN"}),
        )),
        ("codex.sse_event", (
            ("event.kind", {"stringValue": "response.completed"}),
            ("input_token_count", {"stringValue": "9007199254741000"}),
            ("cached_token_count", {"intValue": "9007199254740993"}),
            ("output_token_count", {"stringValue": "200"}),
            ("tool_token_count", {"stringValue": "9007199254741200"}),
        )),
        ("codex.sse_event", (
            ("event.kind", {"stringValue": "response.completed"}),
            ("error.message", {"stringValue": "synthetic-stream-diagnostic"}),
        )),
        ("codex.turn_cost", (
            ("usage.estimated_usd", {"stringValue": "0.123456789012345678"}),
            ("turn.interrupted", {"boolValue": True}),
        )),
        ("codex.api_request", (
            ("http.response.status_code", {"intValue": "500"}),
            ("attempt", {"intValue": "1"}),
        )),
        ("codex.websocket_request", (
            ("success", {"stringValue": "false"}),
            ("duration_ms", {"stringValue": "12.5"}),
        )),
    ):
        records.append({
            "timeUnixNano": "1767226200000000123",
            "eventName": "codex.tool_result" if event == "codex.api_request" else "source-location",
            "attributes": [
                {"key": "event.name", "value": {"stringValue": event}},
                {"key": "tool_name", "value": {"stringValue": "exec_command"}},
                *({"key": key, "value": value} for key, value in attributes),
            ],
        })
    ingestion = httpx.post(
        f"{runtime_endpoints.otlp_base_url}/v1/logs",
        json={"resourceLogs": [{
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": source}}]},
            "scopeLogs": [{"logRecords": records}],
        }]},
        headers={"Authorization": f"Bearer {otlp_bearer_token}"}, timeout=10,
    )
    assert ingestion.status_code == 200, ingestion.text
    response = httpx.post(
        f"{runtime_endpoints.api_base_url}/api/admin/telemetry/log-counts",
        json={
            "time_range": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
            "filters": [{"dimension": "source", "values": [source]}],
            "group_by": ["activity_kind", "outcome"], "bucketing": {"kind": "none"},
            "pagination": {"limit": 100, "offset": 0},
        },
        headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}, timeout=10,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"has_more": False, "rows": [{
        "groups": [
            {"dimension": "activity_kind", "value": {"kind": "missing"}},
            {"dimension": "outcome", "value": {"kind": "missing"}},
        ],
        "count": len(records), "bucket": {"kind": "none"},
    }]}


def test_running_another_harness_declares_activity_and_outcomes(
    runtime_endpoints: RuntimeEndpoints, otlp_bearer_token: str,
) -> None:
    source = f"another-harness-{uuid4().hex}"
    records = []
    for kind, outcome in (
        ("tool_call", "success"), ("file_read", "failure"),
        ("file_edit", "unknown"), ("skill_activation", "success"),
    ):
        records.append({
            "timeUnixNano": "1767226200000000000",
            "eventName": "harness.operation", "severityText": "ERROR",
            "attributes": [
                {"key": "umbod.activity.kind", "value": {"stringValue": kind}},
                {"key": "umbod.activity.outcome", "value": {"stringValue": outcome}},
                {"key": "success", "value": {"boolValue": True}},
                {"key": "mcp.tool.name", "value": {"stringValue": "external_operation"}},
            ],
        })
    ingestion = httpx.post(
        f"{runtime_endpoints.otlp_base_url}/v1/logs",
        json={"resourceLogs": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": source}},
            ]},
            "scopeLogs": [{"logRecords": records}],
        }]},
        headers={"Authorization": f"Bearer {otlp_bearer_token}"}, timeout=10,
    )
    assert ingestion.status_code == 200, ingestion.text
    response = httpx.post(
        f"{runtime_endpoints.api_base_url}/api/admin/telemetry/log-counts",
        json={
            "time_range": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
            "filters": [{"dimension": "source", "values": [source]}],
            "group_by": ["activity_kind", "outcome"], "bucketing": {"kind": "none"},
            "pagination": {"limit": 100, "offset": 0},
        },
        headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}, timeout=10,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"has_more": False, "rows": [
        {
            "groups": [
                {"dimension": "activity_kind", "value": {"kind": "present", "value": kind}},
                {"dimension": "outcome", "value": outcome},
            ],
            "count": 1, "bucket": {"kind": "none"},
        }
        for kind, outcome in (
            ("file_edit", {"kind": "present", "value": "unknown"}),
            ("file_read", {"kind": "present", "value": "failure"}),
            ("skill_activation", {"kind": "missing"}),
            ("tool_call", {"kind": "present", "value": "success"}),
        )
    ]}


def test_running_unified_normalization_keeps_approvals_out_of_execution_counts(
    runtime_endpoints: RuntimeEndpoints, otlp_bearer_token: str,
) -> None:
    source = f"unified-normalization-{uuid4().hex}"
    records = []
    for event in (
        "codex.tool_result", "codex.tool_decision", "claude_code.tool_decision",
        "claude_code.skill_activated", "unsupported.event",
    ):
        records.append({
            "timeUnixNano": "1767226200000000123",
            "observedTimeUnixNano": "1767226200000000456",
            "eventName": "codex.tool_result" if event == "codex.tool_decision" else "source-location",
            "severityNumber": 17,
            "traceId": "0123456789abcdef0123456789abcdef",
            "spanId": "0123456789abcdef",
            "attributes": [
                {"key": "event.name", "value": {"stringValue": event}},
                {"key": "session.id", "value": {"stringValue": "producer-session"}},
                {"key": "conversation.id", "value": {"stringValue": "conversation"}},
                {"key": "mcp.session.id", "value": {"stringValue": "transport-session"}},
                {"key": "tool_name", "value": {"stringValue": "exec_command"}},
                {"key": "call_id", "value": {"stringValue": "reported-call"}},
                {"key": "tool_use_id", "value": {"stringValue": "reported-tool-use"}},
                {"key": "success", "value": {"stringValue": "false"}},
                {"key": "duration_ms", "value": {"stringValue": "NaN"}},
                {"key": "decision", "value": {"stringValue": "accept"}},
                {"key": "app.version", "value": {"boolValue": False}},
            ],
        })
    ingestion = httpx.post(
        f"{runtime_endpoints.otlp_base_url}/v1/logs",
        json={"resourceLogs": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": source}},
                {"key": "service.version", "value": {"stringValue": "fixture-version"}},
            ]},
            "scopeLogs": [{"scope": {"name": "fixture-scope"}, "logRecords": records}],
        }]},
        headers={"Authorization": f"Bearer {otlp_bearer_token}"}, timeout=10,
    )
    assert ingestion.status_code == 200, ingestion.text
    response = httpx.post(
        f"{runtime_endpoints.api_base_url}/api/admin/telemetry/log-counts",
        json={
            "time_range": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
            "filters": [{"dimension": "source", "values": [source]}],
            "group_by": ["activity_kind", "outcome"], "bucketing": {"kind": "none"},
            "pagination": {"limit": 100, "offset": 0},
        },
        headers={"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}, timeout=10,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"has_more": False, "rows": [
        {
            "groups": [
                {"dimension": "activity_kind", "value": {"kind": "missing"}},
                {"dimension": "outcome", "value": {"kind": "missing"}},
            ], "count": 3, "bucket": {"kind": "none"},
        },
        {
            "groups": [
                {"dimension": "activity_kind", "value": {"kind": "present", "value": "skill_activation"}},
                {"dimension": "outcome", "value": {"kind": "missing"}},
            ], "count": 1, "bucket": {"kind": "none"},
        },
        {
            "groups": [
                {"dimension": "activity_kind", "value": {"kind": "present", "value": "tool_call"}},
                {"dimension": "outcome", "value": {"kind": "present", "value": "failure"}},
            ], "count": 1, "bucket": {"kind": "none"},
        },
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
