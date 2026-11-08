import json
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest
from pydantic import JsonValue

from umbod.core.telemetry import TelemetrySignal
from umbod.core.telemetry.analytics import LogDimension
from umbod.core.telemetry.normalization import NormalizedLogRecord
from umbod.core.telemetry.normalization.mapping import normalize_log
from umbod.core.telemetry.normalization.models import PermissionDecision, SkillActivation, ToolActivity
from umbod.core.telemetry.analytics.projection import project_analytics_log
from umbod.rest.telemetry.normalization import normalize_analytics_logs
from umbod.rest.telemetry.validation import parse_export, parse_message, parse_protobuf_export


_RECEIVED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _payload(source: str, event: str, attributes: list[dict[str, JsonValue]]) -> dict[str, JsonValue]:
    return {"resourceLogs": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": source}}]}, "scopeLogs": [{"logRecords": [{"eventName": event, "attributes": attributes}]}]}]}


def _attribute(key: str, value: str) -> dict[str, JsonValue]:
    return {"key": key, "value": {"stringValue": value}}


def _normalized(payload: dict[str, JsonValue]) -> NormalizedLogRecord:
    return cast(NormalizedLogRecord, normalize_analytics_logs(payload, _RECEIVED).records[0].normalization)


def test_pinned_codex_fixture_json_and_protobuf_have_identical_normalization() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "codex_tool_result.json").read_text())
    payload = fixture["payload"]
    binary = parse_message(TelemetrySignal.LOGS, payload).SerializeToString()
    json_export = parse_export(TelemetrySignal.LOGS, json.dumps(payload).encode())
    protobuf_export = parse_protobuf_export(TelemetrySignal.LOGS, binary)
    json_record = _normalized(json_export.payload)
    assert _normalized(protobuf_export.payload) == json_record
    assert json_record.source.record_event.value == "event otel/src/events/session_telemetry.rs:375"
    assert json_record.source.semantic_event.value == "codex.tool_result"
    assert json_record.selected_event.value == "codex.tool_result"
    assert isinstance(json_record.activity, ToolActivity)
    assert json_record.activity.outcome == "failure"
    assert json_record.activity.duration.model_dump() == {"kind": "reported", "value": 12.0, "unit": "milliseconds"}
    assert json_record.timestamps.source_ns == 1001
    assert json_record.timestamps.observed_ns == 2002
    assert json_record.timestamps.receipt_ns == 1767225600000000000
    assert json_record.timestamps.effective_source == "source"
    assert json_record.source.service_version.value == "fixture-build"
    assert json_record.source.app_version.value == "fixture-app"
    assert json_record.source.scope_version.value == "fixture-scope"


def test_documented_claude_skill_fixture_has_identical_json_and_protobuf_trigger_mapping() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "claude_skill_activated.json").read_text())
    payload = fixture["payload"]
    binary = parse_message(TelemetrySignal.LOGS, payload).SerializeToString()
    json_export = parse_export(TelemetrySignal.LOGS, json.dumps(payload).encode())
    protobuf_export = parse_protobuf_export(TelemetrySignal.LOGS, binary)
    normalized = normalize_analytics_logs(json_export.payload, _RECEIVED)
    assert normalize_analytics_logs(protobuf_export.payload, _RECEIVED) == normalized
    records = [cast(NormalizedLogRecord, record.normalization) for record in normalized.records]
    assert [record.activity.trigger for record in records] == ["explicit", "implicit", "nested"]
    assert [record.evidence.skill_trigger for record in records] == ["user-slash", "claude-proactive", "nested-skill"]
    assert all(normalize_log(record.source, record.timestamps, record.evidence) == record for record in records)


def test_source_evidence_replay_and_projection_are_deterministic() -> None:
    record = _normalized(_payload("codex", "metadata", [_attribute("event.name", "codex.tool_result"), _attribute("tool_name", "apply_patch")]))
    restored = NormalizedLogRecord.model_validate_json(record.model_dump_json())
    replayed = normalize_log(restored.source, restored.timestamps, restored.evidence)
    assert replayed == restored
    assert project_analytics_log(replayed) == project_analytics_log(record)


@pytest.mark.parametrize("source,semantic,producer,conflict", [
    ("claude-code", "codex.tool_result", "codex", True),
    ("codex", "claude_code.tool_result", "claude", True),
    ("custom", "codex.tool_result", "codex", False),
])
def test_qualified_semantic_producer_wins_over_service_with_conflict_evidence(
    source: str, semantic: str, producer: str, conflict: bool,
) -> None:
    record = _normalized(_payload(source, "metadata", [_attribute("event.name", semantic)]))
    assert record.mapping.producer == producer
    assert record.mapping.service_conflict is conflict
    assert record.mapping.recognition == "qualified_event"


@pytest.mark.parametrize("source,event,decision,expected", [
    ("claude-code", "tool_decision", "accept", "accept"),
    ("custom", "claude_code.tool_decision", "reject", "reject"),
    ("custom", "tool_decision", "accept", "unmapped"),
    ("codex", "codex.tool_decision", "approved", "accept"),
    ("codex", "codex.tool_decision", "approved_for_session", "accept"),
    ("codex", "codex.tool_decision", "denied", "reject"),
    ("codex", "codex.tool_decision", "accept", "unknown"),
    ("codex", "codex.tool_decision", '{"approved":true}', "unknown"),
])
def test_permission_decisions_do_not_assert_execution_or_add_activity_dimensions(
    source: str, event: str, decision: str, expected: str,
) -> None:
    payload = _payload(source, event, [_attribute("decision", decision), _attribute("tool_name", "apply_patch")])
    batch = normalize_analytics_logs(payload, _RECEIVED)
    record = cast(NormalizedLogRecord, batch.records[0].normalization)
    if expected == "unmapped":
        assert record.activity.kind == "unmapped"
    else:
        assert isinstance(record.activity, PermissionDecision)
        assert record.activity.decision == expected
        assert record.activity.execution == "not_asserted"
    assert LogDimension.ACTIVITY_KIND not in {item.dimension for item in batch.records[0].dimensions}


def test_correlations_remain_distinct_while_legacy_session_precedence_is_unchanged() -> None:
    keys = ("session.id", "session_id", "conversation.id", "conversation_id", "mcp.session.id", "turn.id", "prompt.id", "request.id", "tool_call.id", "call_id", "tool_use_id")
    payload = _payload("codex", "codex.tool_result", [_attribute(key, f"correlation-{index}") for index, key in enumerate(keys)])
    record = _normalized(payload)
    assert {item.key: item.value.value for item in record.evidence.correlations} == {key: f"correlation-{index}" for index, key in enumerate(keys)}
    dimensions = {item.dimension: item.value.value for item in project_analytics_log(record).dimensions}
    assert dimensions[LogDimension.SESSION_ID] == "correlation-0"


@pytest.mark.parametrize("key", ["duration_ms", "decision", "invocation_trigger", "turn.id", "umbod.activity.kind"])
def test_wrong_typed_duplicate_last_value_discards_previous_evidence(key: str) -> None:
    record = _normalized(_payload("codex", "codex.tool_result", [
        _attribute(key, "accept"), {"key": key, "value": {"arrayValue": {"values": [{"stringValue": "PRIVATE_INVALID"}]}}},
    ]))
    assert "PRIVATE_INVALID" not in record.model_dump_json()
    assert "accept" not in record.model_dump_json()


@pytest.mark.parametrize("value,kind", [("-1", "invalid"), ("NaN", "invalid"), ("Infinity", "invalid"), ("junk", "invalid"), ("0", "reported"), ("12.5", "reported")])
def test_duration_semantic_malformation_is_retained_as_invalid_without_rejecting_record(value: str, kind: str) -> None:
    record = _normalized(_payload("codex", "codex.tool_result", [_attribute("duration_ms", value)]))
    assert isinstance(record.activity, ToolActivity)
    assert record.activity.duration.kind == kind


@pytest.mark.parametrize("event,key,value,expected", [
    ("claude_code.skill_activated", "invocation_trigger", "user-slash", "explicit"),
    ("claude_code.skill_activated", "invocation_trigger", "claude-proactive", "implicit"),
    ("claude_code.skill_activated", "invocation_trigger", "nested-skill", "nested"),
    ("claude_code.skill_activated", "trigger", "user-slash", "unknown"),
    ("codex.skill_invocation", "skill.invocation_type", "explicit", "explicit"),
    ("codex.skill_invocation", "skill.invocation_type", "implicit", "implicit"),
    ("codex.skill_invocation", "trigger", "explicit", "unknown"),
    ("codex.skill_invocation", "skill.invocation_type", "PRIVATE_TRIGGER", "unknown"),
])
def test_skill_triggers_use_actual_producer_fields_and_finite_source_enums(event: str, key: str, value: str, expected: str) -> None:
    record = _normalized(_payload("custom", event, [_attribute(key, value)]))
    assert isinstance(record.activity, SkillActivation)
    assert record.activity.trigger == expected
    assert "PRIVATE_TRIGGER" not in record.model_dump_json()
    assert normalize_log(record.source, record.timestamps, record.evidence) == record


@pytest.mark.parametrize("last", [
    {"boolValue": True},
    {"stringValue": "PRIVATE_INVALID_TRIGGER"},
    {"arrayValue": {"values": [{"stringValue": "PRIVATE_INVALID_TRIGGER"}]}},
])
def test_claude_invocation_trigger_invalid_duplicate_last_does_not_restore_previous_value(last: dict[str, JsonValue]) -> None:
    record = _normalized(_payload("claude-code", "claude_code.skill_activated", [
        _attribute("invocation_trigger", "user-slash"),
        {"key": "invocation_trigger", "value": last},
    ]))
    assert isinstance(record.activity, SkillActivation)
    assert record.activity.trigger == "unknown"
    assert record.evidence.skill_trigger == "unknown"
    assert "PRIVATE_INVALID_TRIGGER" not in record.model_dump_json()
    assert normalize_log(record.source, record.timestamps, record.evidence) == record


def test_skill_activation_never_retains_identity_or_inventory() -> None:
    record = _normalized(_payload("codex", "codex.skill_invocation", [
        _attribute("skill.invocation_type", "explicit"), _attribute("skill.name", "PRIVATE_SKILL"),
        _attribute("plugin.id", "PRIVATE_PLUGIN"), _attribute("skill_inventory", "PRIVATE_INVENTORY"),
    ]))
    assert isinstance(record.activity, SkillActivation)
    assert record.activity.trigger == "explicit"
    assert "PRIVATE" not in record.model_dump_json()


def test_log_body_and_scope_attributes_are_not_retained() -> None:
    payload: dict[str, JsonValue] = {"resourceLogs": [{"scopeLogs": [{
        "scope": {"attributes": [_attribute("private.inventory", "PRIVATE_SCOPE")]},
        "logRecords": [{"body": {"stringValue": "PRIVATE_BODY"}}],
    }]}]}
    assert "PRIVATE" not in _normalized(payload).model_dump_json()


def test_wrong_typed_mcp_tool_name_does_not_become_external_provenance() -> None:
    record = _normalized(_payload("codex", "codex.tool_result", [
        _attribute("tool_name", "apply_patch"), _attribute("mcp.tool.name", "external"),
        {"key": "mcp.tool.name", "value": {"boolValue": True}},
    ]))
    assert isinstance(record.activity, ToolActivity)
    assert record.activity.activity_kind == "file_edit"
    assert record.evidence.tool_provenance.origin == "native"


def test_unapproved_private_data_and_raw_origin_are_absent_from_normalized_json() -> None:
    private_keys = ("body", "prompt", "arguments", "output", "file.path", "email", "user.id", "account.id", "skill_name", "plugin_id", "arbitrary")
    attributes = [_attribute(key, f"PRIVATE_{index}") for index, key in enumerate(private_keys)]
    attributes.extend([_attribute("mcp_server_origin", "https://PRIVATE_ORIGIN.example"), _attribute("mcp_server", "PRIVATE_SERVER")])
    payload = _payload("codex", "codex.tool_result", attributes)
    record = _normalized(payload)
    assert record.evidence.tool_provenance.origin == "external"
    assert record.evidence.tool_provenance.basis == "explicit"
    assert "PRIVATE" not in record.model_dump_json()


def test_oversized_new_metadata_is_explicitly_invalid_and_not_truncated() -> None:
    private = "PRIVATE_OVERSIZE" * 100
    record = _normalized(_payload("codex", "codex.tool_result", [_attribute("turn.id", private)]))
    assert record.evidence.correlations[0].value.model_dump() == {"kind": "invalid", "reason": "oversize"}
    assert "PRIVATE_OVERSIZE" not in record.model_dump_json()


def test_unmapped_record_is_retained_with_explicit_mapping_status() -> None:
    record = _normalized(_payload("custom", "diagnostic", []))
    assert record.activity.kind == "unmapped"
    assert record.mapping.mapping_id == "unmapped"
    assert record.schema_version == record.evidence.schema_version == record.mapping.mapping_version == 2


@pytest.mark.parametrize("schema_url", [
    "https://opentelemetry.io/schemas/1.9.0",
    "https://opentelemetry.io/schemas/1.30.0",
    "https://opentelemetry.io/schemas/1.40.0",
])
def test_versioned_schema_urls_preserve_approved_namespace_without_a_single_version_pin(schema_url: str) -> None:
    payload: dict[str, JsonValue] = {"resourceLogs": [{"schemaUrl": schema_url, "scopeLogs": [{"schemaUrl": schema_url, "logRecords": [{}]}]}]}
    record = _normalized(payload)
    assert record.source.resource_schema_url.model_dump() == {"kind": "text", "value": schema_url}
    assert record.source.scope_schema_url.model_dump() == {"kind": "text", "value": schema_url}
    assert NormalizedLogRecord.model_validate_json(record.model_dump_json()) == record


@pytest.mark.parametrize("schema_url", [
    "PRIVATE_SCHEMA_URL", "https://PRIVATE_SCHEMA_URL.example/schema",
    "https://PRIVATE_SCHEMA_URL@opentelemetry.io/schemas/1.30.0",
    "https://opentelemetry.io/schemas/1.30.0?token=PRIVATE_SCHEMA_URL",
    "https://opentelemetry.io/schemas/1.30.0#PRIVATE_SCHEMA_URL",
])
def test_schema_urls_never_retain_private_urls_credentials_queries_or_fragments(schema_url: str) -> None:
    payload: dict[str, JsonValue] = {"resourceLogs": [{"schemaUrl": schema_url, "scopeLogs": [{"schemaUrl": schema_url, "logRecords": [{}]}]}]}
    record = _normalized(payload)
    assert record.source.resource_schema_url.model_dump() == {"kind": "invalid", "reason": "unrecognized"}
    assert record.source.scope_schema_url.model_dump() == {"kind": "invalid", "reason": "unrecognized"}
    assert "PRIVATE_SCHEMA_URL" not in record.model_dump_json()


def test_native_trace_ids_are_not_fabricated_from_log_attributes() -> None:
    record = _normalized(_payload("codex", "codex.tool_result", [
        _attribute("trace_id", "PRIVATE_TRACE"), _attribute("span_id", "PRIVATE_SPAN"),
    ]))
    assert record.evidence.correlations == ()
    assert "PRIVATE" not in record.model_dump_json()


def test_unqualified_duration_does_not_assume_units() -> None:
    record = _normalized(_payload("codex", "codex.tool_result", [_attribute("duration", "12")]))
    assert record.evidence.duration.model_dump() == {"kind": "invalid", "reason": "unrecognized"}


def test_oversized_source_metadata_is_omitted_without_failing_ingestion() -> None:
    private = "PRIVATE_VERSION" * 100
    payload: dict[str, JsonValue] = {"resourceLogs": [{"resource": {"attributes": [_attribute("service.version", private)]}, "scopeLogs": [{"scope": {"name": private, "version": private}, "logRecords": [{"attributes": [_attribute("app.version", private)]}]}]}]}
    record = _normalized(payload)
    for field in (record.source.service_version, record.source.app_version, record.source.scope_name, record.source.scope_version):
        assert field.model_dump() == {"kind": "invalid", "reason": "oversize"}
    assert "PRIVATE_VERSION" not in record.model_dump_json()


def test_legacy_dimension_strings_keep_their_original_acceptance_and_alias_behavior() -> None:
    value = "legacy" * 200
    record = _normalized(_payload(value, value, [_attribute("session.id", value), _attribute("tool.name", value)]))
    assert {item.dimension: item.value.value for item in project_analytics_log(record).dimensions} == {
        LogDimension.SOURCE: value, LogDimension.EVENT_NAME: value,
        LogDimension.SESSION_ID: value, LogDimension.TOOL_NAME: value,
    }


def test_unknown_numeric_severity_is_explicitly_invalid_without_a_server_error() -> None:
    payload: dict[str, JsonValue] = {"resourceLogs": [{"scopeLogs": [{"logRecords": [{"severityNumber": 100}]}]}]}
    record = _normalized(payload)
    assert record.source.severity_number.model_dump() == {"kind": "invalid", "reason": "out_of_range"}
