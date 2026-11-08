import json
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest
from pydantic import JsonValue

from umbod.core.telemetry import TelemetrySignal
from umbod.core.telemetry.analytics import LogDimension
from umbod.core.telemetry.analytics.projection import project_analytics_log
from umbod.core.telemetry.normalization import NormalizedLogRecord
from umbod.core.telemetry.normalization.mapping import normalize_log
from umbod.core.telemetry.normalization.models import ModelRequest, ReportedBoolean
from umbod.rest.telemetry.normalization import normalize_analytics_logs
from umbod.rest.telemetry.validation import parse_export, parse_message, parse_protobuf_export


_RECEIVED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _payload(name: str) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], json.loads((Path(__file__).parent / "fixtures" / name).read_text())["payload"])


def _record(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0])


def _append(payload: dict[str, JsonValue], key: str, value: dict[str, JsonValue]) -> None:
    cast(list[dict[str, JsonValue]], _record(payload)["attributes"]).append({"key": key, "value": value})


def _normalize(payload: dict[str, JsonValue]) -> NormalizedLogRecord:
    return cast(NormalizedLogRecord, normalize_analytics_logs(payload, _RECEIVED).records[0].normalization)


@pytest.mark.parametrize("fixture,kind", [
    ("claude_model_request.json", "model_request"),
    ("codex_response_usage.json", "response_usage"),
])
def test_documented_request_usage_contracts_have_identical_json_and_protobuf_normalization(fixture: str, kind: str) -> None:
    payload = _payload(fixture)
    binary = parse_message(TelemetrySignal.LOGS, payload).SerializeToString()
    json_export = parse_export(TelemetrySignal.LOGS, json.dumps(payload).encode())
    protobuf_export = parse_protobuf_export(TelemetrySignal.LOGS, binary)
    record = _normalize(json_export.payload)
    assert _normalize(protobuf_export.payload) == record
    assert record.schema_version == record.evidence.schema_version == record.mapping.mapping_version == 2
    assert record.activity.kind == kind
    assert normalize_log(record.source, record.timestamps, record.evidence) == record
    projected = project_analytics_log(record)
    assert projected.owner.kind == "unowned"
    assert LogDimension.ACTIVITY_KIND not in {group.dimension for group in projected.dimensions}
    assert LogDimension.OUTCOME not in {group.dimension for group in projected.dimensions}


@pytest.mark.parametrize("encoding", ["json", "protobuf"])
def test_native_integer_usage_beyond_double_precision_is_not_rounded(encoding: str) -> None:
    payload = _payload("codex_response_usage.json")
    _append(payload, "cached_token_count", {"intValue": "9007199254740993"})
    if encoding == "protobuf":
        binary = parse_message(TelemetrySignal.LOGS, payload).SerializeToString()
        payload = parse_protobuf_export(TelemetrySignal.LOGS, binary).payload
    record = _normalize(payload)
    assert "9007199254740993" in record.model_dump_json()
    assert normalize_log(record.source, record.timestamps, record.evidence) == record


@pytest.mark.parametrize("last", [
    {"boolValue": True},
    {"stringValue": "PRIVATE_INVALID_TOKEN"},
    {"arrayValue": {"values": [{"stringValue": "PRIVATE_INVALID_TOKEN"}]}},
])
def test_invalid_last_duplicate_token_replaces_earlier_valid_value_without_retaining_content(last: dict[str, JsonValue]) -> None:
    payload = _payload("codex_response_usage.json")
    _append(payload, "cached_token_count", {"intValue": "987654321"})
    _append(payload, "cached_token_count", last)
    serialized = _normalize(payload).model_dump_json()
    assert "987654321" not in serialized
    assert "PRIVATE_INVALID_TOKEN" not in serialized
    assert '"kind":"invalid"' in serialized


@pytest.mark.parametrize("event", ["claude_code.api_error", "codex.api_request"])
def test_request_normalization_keeps_no_errors_content_endpoints_or_private_model_identifiers(event: str) -> None:
    payload = _payload("claude_model_request.json")
    record = _record(payload)
    record["eventName"] = event
    record["body"] = {"stringValue": "PRIVATE_BODY"}
    for key, value in (
        ("event.name", event), ("model", "../PRIVATE_MODEL"),
        ("slug", "arn:aws:bedrock:region:PRIVATE_ACCOUNT:model"),
        ("error", "PRIVATE_ERROR"), ("error.message", "PRIVATE_ERROR_MESSAGE"),
        ("endpoint", "https://PRIVATE_ENDPOINT/path"),
        ("query_source", "PRIVATE_SUBAGENT"), ("user.id", "PRIVATE_USER"),
        ("request.headers", "PRIVATE_HEADERS"), ("prompt", "PRIVATE_PROMPT"),
    ):
        _append(payload, key, {"stringValue": value})
    normalized = _normalize(payload)
    assert normalized.activity.kind == "model_request"
    assert "PRIVATE_" not in normalized.model_dump_json()


@pytest.mark.parametrize("error", ["", "   ", "synthetic-error"])
def test_empty_error_message_still_preserves_error_presence_without_content(error: str) -> None:
    payload = _payload("codex_response_usage.json")
    record = _record(payload)
    record["eventName"] = "codex.api_request"
    record["attributes"] = [
        {"key": "event.name", "value": {"stringValue": "codex.api_request"}},
        {"key": "error.message", "value": {"stringValue": error}},
        {"key": "http.response.status_code", "value": {"intValue": "200"}},
    ]
    activity = _normalize(payload).activity
    assert isinstance(activity, ModelRequest)
    assert activity.error_indicator == ReportedBoolean(kind="boolean", value=True)
    assert activity.transport_outcome == "failure"
    assert "synthetic-error" not in activity.model_dump_json()


@pytest.mark.parametrize("kind", ["response.completed", "PRIVATE_UNKNOWN_EVENT"])
def test_stream_kind_without_usage_does_not_manufacture_response_usage(kind: str) -> None:
    payload = _payload("codex_response_usage.json")
    record = _record(payload)
    record["attributes"] = [
        {"key": "event.name", "value": {"stringValue": "codex.sse_event"}},
        {"key": "event.kind", "value": {"stringValue": kind}},
        {"key": "error.message", "value": {"stringValue": "PRIVATE_STREAM_ERROR"}},
    ]
    normalized = _normalize(payload)
    assert normalized.activity.kind != "response_usage"
    assert "PRIVATE_" not in normalized.model_dump_json()


def test_model_request_semantic_identity_prevents_conflicting_raw_tool_execution() -> None:
    payload = _payload("claude_model_request.json")
    _record(payload)["eventName"] = "claude_code.tool_result"
    _append(payload, "tool_name", {"stringValue": "Read"})
    _append(payload, "success", {"boolValue": True})
    record = _normalize(payload)
    assert record.activity.kind == "model_request"
    assert record.mapping.event_identity_conflict is True
    assert LogDimension.ACTIVITY_KIND not in {group.dimension for group in project_analytics_log(record).dimensions}
