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


def test_null_collections_and_unknown_fields_follow_receiver_validation() -> None:
    payload: dict[str, JsonValue] = {"resourceLogs": None, "unknown": {"attributes": "ignored"}}
    assert normalize_analytics_logs(payload, _RECEIVED).records == ()
