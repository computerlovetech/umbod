from datetime import datetime, timedelta, timezone

import pytest
from pydantic import JsonValue

from umbod.core.telemetry.analytics import LogDimension, UnownedLog
from umbod.rest.telemetry.normalization import normalize_analytics_logs


_RECEIVED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _export(record: dict[str, JsonValue], resource: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"resourceLogs": [{"resource": resource, "scopeLogs": [{"logRecords": [record]}]}]}


@pytest.mark.parametrize("record,expected", [
    ({"timeUnixNano": "1001", "observedTimeUnixNano": "9000"}, datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=1)),
    ({"observedTimeUnixNano": "9000"}, datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=9)),
    ({}, _RECEIVED),
    ({"timeUnixNano": "18446744073709551615"}, datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=18446744073709551)),
])
def test_timestamps_use_source_then_observed_then_receipt_without_float_rounding(
    record: dict[str, JsonValue], expected: datetime,
) -> None:
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    assert batch.records[0].occurred_at == expected


def test_event_field_overrides_attribute_and_resource_controls_source() -> None:
    record: dict[str, JsonValue] = {
        "eventName": "canonical-event",
        "severityText": "ERROR",
        "attributes": [
            {"key": "event.name", "value": {"stringValue": "attribute-event"}},
            {"key": "service.name", "value": {"stringValue": "spoofed-source"}},
            {"key": "conversation.id", "value": {"stringValue": "session"}},
            {"key": "tool_name", "value": {"stringValue": "shell"}},
        ],
    }
    resource: dict[str, JsonValue] = {"attributes": [
        {"key": "service.name", "value": {"stringValue": "codex"}},
    ]}
    batch = normalize_analytics_logs(_export(record, resource), _RECEIVED)
    values = {group.dimension: group.value.value for group in batch.records[0].dimensions}
    assert values == {
        LogDimension.SOURCE: "codex", LogDimension.EVENT_NAME: "canonical-event",
        LogDimension.SEVERITY: "ERROR", LogDimension.SESSION_ID: "session", LogDimension.TOOL_NAME: "shell",
    }


@pytest.mark.parametrize("source,record_event,semantic_event,tool,kind", [
    ("codex_exec", "event otel/src/events/session_telemetry.rs:375", "codex.tool_result", "apply_patch", "file_edit"),
    ("codex_exec", "event otel/src/events/session_telemetry.rs:375", "codex.tool_result", "exec_command", "tool_call"),
    ("claude-code", "generic metadata", "tool_result", "Read", "file_read"),
    ("claude-code", "generic metadata", "tool_result", "Edit", "file_edit"),
    ("custom", "codex.tool_result", "unrecognized", "apply_patch", "file_edit"),
    ("custom", "codex.tool_result", "claude_code.tool_result", "Read", "file_read"),
    ("custom", "claude_code.tool_result", "codex.skill_invocation", "Read", "skill_activation"),
    ("codex_exec", "event otel/src/events/session_telemetry.rs:375", "", "apply_patch", ""),
])
def test_semantic_event_classification_precedes_metadata_without_changing_raw_dimension(
    source: str, record_event: str, semantic_event: str, tool: str, kind: str,
) -> None:
    record: dict[str, JsonValue] = {
        "eventName": record_event,
        "attributes": [
            {"key": "event.name", "value": {"stringValue": semantic_event}},
            {"key": "tool_name", "value": {"stringValue": tool}},
            {"key": "success", "value": {"boolValue": False}},
        ],
    }
    resource: dict[str, JsonValue] = {"attributes": [
        {"key": "service.name", "value": {"stringValue": source}},
    ]}
    batch = normalize_analytics_logs(_export(record, resource), _RECEIVED)
    expected = {
        LogDimension.SOURCE: source, LogDimension.EVENT_NAME: record_event,
        LogDimension.TOOL_NAME: tool,
    }
    if kind:
        expected[LogDimension.ACTIVITY_KIND] = kind
        if kind != "skill_activation":
            expected[LogDimension.OUTCOME] = "failure"
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == expected


def test_explicit_declaration_precedes_both_recognized_event_candidates() -> None:
    record: dict[str, JsonValue] = {
        "eventName": "claude_code.tool_result",
        "attributes": [
            {"key": "event.name", "value": {"stringValue": "codex.skill_invocation"}},
            {"key": "tool_name", "value": {"stringValue": "Read"}},
            {"key": "umbod.activity.kind", "value": {"stringValue": "file_edit"}},
            {"key": "umbod.activity.outcome", "value": {"stringValue": "failure"}},
            {"key": "success", "value": {"boolValue": True}},
        ],
    }
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == {
        LogDimension.EVENT_NAME: "claude_code.tool_result", LogDimension.TOOL_NAME: "Read",
        LogDimension.ACTIVITY_KIND: "file_edit", LogDimension.OUTCOME: "failure",
    }


def test_attribute_last_occurrence_wins_and_nonstring_values_are_missing() -> None:
    record: dict[str, JsonValue] = {"attributes": [
        {"key": "tool.name", "value": {"stringValue": "old"}},
        {"key": "tool.name", "value": {"stringValue": ""}},
        {"key": "event.name", "value": {"stringValue": "old-event"}},
        {"key": "event.name", "value": {"intValue": "1"}},
    ]}
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    assert tuple((group.dimension, group.value.value) for group in batch.records[0].dimensions) == (
        (LogDimension.TOOL_NAME, ""),
    )


def test_identity_attributes_and_log_body_are_not_retained_as_analytics_fields() -> None:
    record: dict[str, JsonValue] = {
        "body": {"stringValue": "private prompt"},
        "attributes": [{"key": "enduser.id", "value": {"stringValue": "untrusted-user"}}],
    }
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    assert batch.records[0].owner == UnownedLog(kind="unowned")
    assert "private prompt" not in batch.model_dump_json()


@pytest.mark.parametrize("success,expected", [
    ({"boolValue": True}, "success"),
    ({"boolValue": False}, "failure"),
    ({"stringValue": "true"}, "success"),
    ({"stringValue": "false"}, "failure"),
    ({"stringValue": "False"}, "unknown"),
    ({"stringValue": ""}, "unknown"),
    ({"intValue": "1"}, "unknown"),
    ({}, "unknown"),
])
@pytest.mark.parametrize("severity", ["INFO", "ERROR"])
def test_outcomes_use_exact_success_attribute_not_severity(
    success: dict[str, JsonValue], expected: str, severity: str,
) -> None:
    record: dict[str, JsonValue] = {
        "eventName": "claude_code.tool_result", "severityText": severity,
        "body": {"stringValue": "discarded body"},
        "attributes": [
            {"key": "tool_name", "value": {"stringValue": "Read"}},
            {"key": "success", "value": success},
            {"key": "tool_parameters", "value": {"stringValue": "discarded arguments"}},
        ],
    }
    resource: dict[str, JsonValue] = {"attributes": [
        {"key": "service.name", "value": {"stringValue": "custom"}},
    ]}
    batch = normalize_analytics_logs(_export(record, resource), _RECEIVED)
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == {
        LogDimension.SOURCE: "custom", LogDimension.EVENT_NAME: "claude_code.tool_result",
        LogDimension.SEVERITY: severity, LogDimension.TOOL_NAME: "Read",
        LogDimension.ACTIVITY_KIND: "file_read", LogDimension.OUTCOME: expected,
    }
    assert "discarded" not in batch.model_dump_json()


def test_success_duplicate_last_occurrence_wins_even_when_malformed() -> None:
    record: dict[str, JsonValue] = {
        "eventName": "codex.tool_result",
        "attributes": [
            {"key": "success", "value": {"boolValue": True}},
            {"key": "success", "value": {"stringValue": "false"}},
        ],
    }
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    assert batch.records[0].dimensions[-1].value.value == "failure"
    record["attributes"].append({"key": "success", "value": {"intValue": "1"}})
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    assert batch.records[0].dimensions[-1].value.value == "unknown"


@pytest.mark.parametrize("key", [
    "tool_type", "tool.kind", "mcp.server.name", "mcp_server", "mcp_server_origin", "tool_namespace", "mcp.tool.name",
])
def test_external_tool_metadata_prevents_native_codex_name_promotion(key: str) -> None:
    record: dict[str, JsonValue] = {
        "eventName": "codex.tool_result",
        "attributes": [
            {"key": "tool_name", "value": {"stringValue": "apply_patch"}},
            {"key": key, "value": {"stringValue": "mcp"}},
        ],
    }
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == {
        LogDimension.EVENT_NAME: "codex.tool_result", LogDimension.TOOL_NAME: "apply_patch",
        LogDimension.ACTIVITY_KIND: "tool_call", LogDimension.OUTCOME: "unknown",
    }


@pytest.mark.parametrize("key,value", [
    ("mcp.session.id", "session"),
    ("mcp_server", ""),
    ("mcp_server_origin", ""),
    ("tool_namespace", "native"),
    ("tool_namespace", ""),
    ("tool_namespace", "functions"),
])
def test_nonprovenance_metadata_does_not_demote_native_codex_file_edit(
    key: str, value: str,
) -> None:
    record: dict[str, JsonValue] = {
        "eventName": "codex.tool_result",
        "attributes": [
            {"key": "tool_name", "value": {"stringValue": "apply_patch"}},
            {"key": "success", "value": {"boolValue": False}},
            {"key": key, "value": {"stringValue": value}},
        ],
    }
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    expected = {
        LogDimension.EVENT_NAME: "codex.tool_result", LogDimension.TOOL_NAME: "apply_patch",
        LogDimension.ACTIVITY_KIND: "file_edit", LogDimension.OUTCOME: "failure",
    }
    if key == "mcp.session.id":
        expected[LogDimension.SESSION_ID] = "session"
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == expected


def test_custom_tool_namespace_prevents_codex_native_name_promotion() -> None:
    record: dict[str, JsonValue] = {
        "eventName": "codex.tool_result",
        "attributes": [
            {"key": "tool_name", "value": {"stringValue": "apply_patch"}},
            {"key": "tool_namespace", "value": {"stringValue": "custom"}},
        ],
    }
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    values = {group.dimension: group.value.value for group in batch.records[0].dimensions}
    assert values[LogDimension.ACTIVITY_KIND] == "tool_call"


@pytest.mark.parametrize("kind", ["tool_call", "file_read", "file_edit", "skill_activation"])
def test_declared_kind_overrides_legacy_and_external_provenance_without_retaining_private_fields(
    kind: str,
) -> None:
    record: dict[str, JsonValue] = {
        "eventName": "claude_code.tool_result",
        "body": {"stringValue": "private body"},
        "attributes": [
            {"key": "tool.name", "value": {"stringValue": "Read"}},
            {"key": "mcp_server", "value": {"stringValue": "private server"}},
            {"key": "umbod.activity.kind", "value": {"stringValue": kind}},
            {"key": "umbod.activity.outcome", "value": {"stringValue": "failure"}},
            {"key": "success", "value": {"boolValue": True}},
            {"key": "arguments", "value": {"stringValue": "private arguments"}},
            {"key": "file.path", "value": {"stringValue": "private path"}},
            {"key": "skill.name", "value": {"stringValue": "private skill"}},
        ],
    }
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    expected = {
        LogDimension.EVENT_NAME: "claude_code.tool_result", LogDimension.TOOL_NAME: "Read",
        LogDimension.ACTIVITY_KIND: kind,
    }
    if kind != "skill_activation":
        expected[LogDimension.OUTCOME] = "failure"
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == expected
    assert batch.records[0].owner == UnownedLog(kind="unowned")
    assert "private" not in batch.model_dump_json()


@pytest.mark.parametrize("canonical,expected", [
    ({"stringValue": "success"}, "success"),
    ({"stringValue": "failure"}, "failure"),
    ({"stringValue": "unknown"}, "unknown"),
    ({"stringValue": "Success"}, "unknown"),
    ({"stringValue": "success "}, "unknown"),
    ({"stringValue": ""}, "unknown"),
    ({"boolValue": True}, "unknown"),
    ({"intValue": "1"}, "unknown"),
    ({}, "unknown"),
])
def test_declared_outcome_last_duplicate_overrides_success_even_when_invalid(
    canonical: dict[str, JsonValue], expected: str,
) -> None:
    record: dict[str, JsonValue] = {
        "eventName": "arbitrary-harness-event", "severityText": "ERROR",
        "attributes": [
            {"key": "umbod.activity.kind", "value": {"stringValue": "file_edit"}},
            {"key": "success", "value": {"boolValue": True}},
            {"key": "umbod.activity.outcome", "value": {"stringValue": "failure"}},
            {"key": "umbod.activity.outcome", "value": canonical},
        ],
    }
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == {
        LogDimension.EVENT_NAME: "arbitrary-harness-event", LogDimension.SEVERITY: "ERROR",
        LogDimension.ACTIVITY_KIND: "file_edit", LogDimension.OUTCOME: expected,
    }


@pytest.mark.parametrize("success,expected", [
    ({"boolValue": True}, "success"), ({"boolValue": False}, "failure"),
    ({"stringValue": "true"}, "success"), ({"stringValue": "false"}, "failure"),
    ({"stringValue": "TRUE"}, "unknown"), ({}, "unknown"),
])
def test_declared_tools_without_canonical_outcome_fall_back_to_explicit_success(
    success: dict[str, JsonValue], expected: str,
) -> None:
    record: dict[str, JsonValue] = {"severityText": "ERROR", "attributes": [
        {"key": "umbod.activity.kind", "value": {"stringValue": "tool_call"}},
        {"key": "success", "value": success},
    ]}
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == {
        LogDimension.SEVERITY: "ERROR", LogDimension.ACTIVITY_KIND: "tool_call",
        LogDimension.OUTCOME: expected,
    }


@pytest.mark.parametrize("declared", [
    {"stringValue": "file_read"}, {"stringValue": "invalid"},
    {"stringValue": "File_edit"}, {"stringValue": "file_edit "},
    {"boolValue": True}, {"intValue": "1"}, {},
])
@pytest.mark.parametrize("event", ["codex.tool_result", "diagnostic"])
def test_last_declared_kind_controls_classification_or_unchanged_legacy_fallback(
    declared: dict[str, JsonValue], event: str,
) -> None:
    record: dict[str, JsonValue] = {"eventName": event, "attributes": [
        {"key": "tool.name", "value": {"stringValue": "apply_patch"}},
        {"key": "umbod.activity.kind", "value": {"stringValue": "skill_activation"}},
        {"key": "umbod.activity.kind", "value": declared},
        {"key": "umbod.activity.outcome", "value": {"stringValue": "failure"}},
        {"key": "success", "value": {"boolValue": True}},
    ]}
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    expected = {LogDimension.EVENT_NAME: event, LogDimension.TOOL_NAME: "apply_patch"}
    if declared == {"stringValue": "file_read"}:
        expected.update({LogDimension.ACTIVITY_KIND: "file_read", LogDimension.OUTCOME: "failure"})
    elif event == "codex.tool_result":
        expected.update({LogDimension.ACTIVITY_KIND: "file_edit", LogDimension.OUTCOME: "success"})
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == expected


def test_canonical_outcome_without_declared_kind_does_not_change_legacy_outcome() -> None:
    record: dict[str, JsonValue] = {"eventName": "codex.tool_result", "attributes": [
        {"key": "umbod.activity.outcome", "value": {"stringValue": "failure"}},
        {"key": "success", "value": {"boolValue": True}},
    ]}
    batch = normalize_analytics_logs(_export(record, {}), _RECEIVED)
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == {
        LogDimension.EVENT_NAME: "codex.tool_result",
        LogDimension.ACTIVITY_KIND: "tool_call", LogDimension.OUTCOME: "success",
    }


@pytest.mark.parametrize("kind", ["tool_call", "file_read", "file_edit", "skill_activation"])
def test_any_harness_can_declare_activity_without_tool_or_event_metadata(kind: str) -> None:
    record: dict[str, JsonValue] = {"attributes": [
        {"key": "umbod.activity.kind", "value": {"stringValue": kind}},
    ]}
    resource: dict[str, JsonValue] = {"attributes": [
        {"key": "service.name", "value": {"stringValue": "another-harness"}},
    ]}
    batch = normalize_analytics_logs(_export(record, resource), _RECEIVED)
    expected = {LogDimension.SOURCE: "another-harness", LogDimension.ACTIVITY_KIND: kind}
    if kind != "skill_activation":
        expected[LogDimension.OUTCOME] = "unknown"
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == expected


@pytest.mark.parametrize("source,event,tool", [
    ("codex_exec", "event otel/src/events/session_telemetry.rs:375", ""),
    ("codex_exec", "event otel/src/events/session_telemetry.rs:412", "apply_patch"),
    ("codex_exec", "event otel/src/metrics.rs:90", "Read"),
    ("codex_exec", "event core/src/provider.rs:120", "Edit"),
    ("ui-check", "tool_result", "Read"),
    ("ui-check", "synthetic", "apply_patch"),
    ("", "", ""),
])
def test_diagnostics_and_synthetic_records_are_stored_without_activity_inference(
    source: str, event: str, tool: str,
) -> None:
    record: dict[str, JsonValue] = {"attributes": [
        {"key": "event.name", "value": {"stringValue": event}},
        {"key": "tool.name", "value": {"stringValue": tool}},
        {"key": "umbod.activity.outcome", "value": {"stringValue": "success"}},
    ]}
    resource: dict[str, JsonValue] = {"attributes": [
        {"key": "service.name", "value": {"stringValue": source}},
    ]}
    batch = normalize_analytics_logs(_export(record, resource), _RECEIVED)
    assert len(batch.records) == 1
    assert {group.dimension: group.value.value for group in batch.records[0].dimensions} == {
        LogDimension.SOURCE: source, LogDimension.EVENT_NAME: event, LogDimension.TOOL_NAME: tool,
    }


def test_null_collections_and_unknown_fields_follow_receiver_validation() -> None:
    payload: dict[str, JsonValue] = {"resourceLogs": None, "unknown": {"attributes": "ignored"}}
    assert normalize_analytics_logs(payload, _RECEIVED).records == ()
