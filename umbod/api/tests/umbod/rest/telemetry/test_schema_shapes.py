import json

import pytest
from pydantic import JsonValue

from umbod.core.telemetry import TelemetrySignal
from umbod.rest.telemetry.errors import TelemetryHttpError
from umbod.rest.telemetry.validation import parse_export


@pytest.mark.parametrize("resource", ["unknown", [], 1, False])
def test_recognized_message_requires_object(resource: JsonValue) -> None:
    body = json.dumps({"resourceLogs": [{"resource": resource}]}).encode()
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(TelemetrySignal.LOGS, body)
    assert error.value.status_code == 400


@pytest.mark.parametrize("value", ["unknown", {}, 1, False])
def test_recognized_repeated_message_requires_array(value: JsonValue) -> None:
    body = json.dumps({"resourceLogs": value}).encode()
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(TelemetrySignal.LOGS, body)
    assert error.value.status_code == 400


@pytest.mark.parametrize("value", [1, True, [], {}])
def test_anyvalue_string_rejects_nonstring(value: JsonValue) -> None:
    body = json.dumps(
        {
            "resourceLogs": [
                {"scopeLogs": [{"logRecords": [{"body": {"stringValue": value}}]}]}
            ]
        }
    ).encode()
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(TelemetrySignal.LOGS, body)
    assert error.value.status_code == 400


@pytest.mark.parametrize(
    "record",
    [
        {"severityNumber": None},
        {"traceId": None, "spanId": None},
        {"timeUnixNano": None, "severityText": None},
        {"body": None, "attributes": None},
        {"body": {"bytesValue": None}},
        {"body": {"doubleValue": None, "intValue": None, "boolValue": None}},
        {"body": {"stringValue": None, "intValue": "1"}},
        {"body": {"arrayValue": {"values": None}}},
    ],
)
def test_known_null_fields_are_unset_and_source_is_preserved(
    record: dict[str, JsonValue],
) -> None:
    payload = {
        "resourceLogs": [{"resource": None, "scopeLogs": [{"logRecords": [record]}]}]
    }
    batch = parse_export(TelemetrySignal.LOGS, json.dumps(payload).encode())
    assert batch.item_count == 1
    assert batch.payload == payload


@pytest.mark.parametrize(
    "signal,field",
    [
        (TelemetrySignal.LOGS, "resourceLogs"),
        (TelemetrySignal.TRACES, "resourceSpans"),
        (TelemetrySignal.METRICS, "resourceMetrics"),
    ],
)
def test_null_export_collection_is_unset(signal: TelemetrySignal, field: str) -> None:
    payload = {field: None}
    batch = parse_export(signal, json.dumps(payload).encode())
    assert batch.item_count == 0
    assert batch.payload == payload


@pytest.mark.parametrize(
    "signal,payload",
    [
        (TelemetrySignal.LOGS, {"resourceLogs": [None]}),
        (TelemetrySignal.TRACES, {"resourceSpans": [{"scopeSpans": [None]}]}),
        (
            TelemetrySignal.LOGS,
            {"resourceLogs": [{"scopeLogs": [{"logRecords": [None]}]}]},
        ),
        (
            TelemetrySignal.LOGS,
            {"resourceLogs": [{"resource": {"attributes": [None]}}]},
        ),
        (
            TelemetrySignal.LOGS,
            {
                "resourceLogs": [
                    {
                        "scopeLogs": [
                            {
                                "logRecords": [
                                    {"body": {"arrayValue": {"values": [None]}}}
                                ]
                            }
                        ]
                    }
                ]
            },
        ),
        (
            TelemetrySignal.METRICS,
            {
                "resourceMetrics": [
                    {
                        "scopeMetrics": [
                            {
                                "metrics": [
                                    {
                                        "histogram": {
                                            "dataPoints": [{"bucketCounts": [None]}]
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
        ),
        (
            TelemetrySignal.METRICS,
            {
                "resourceMetrics": [
                    {
                        "scopeMetrics": [
                            {
                                "metrics": [
                                    {
                                        "histogram": {
                                            "dataPoints": [{"explicitBounds": [None]}]
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
        ),
    ],
)
def test_repeated_fields_reject_null_elements(
    signal: TelemetrySignal, payload: dict[str, JsonValue]
) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(signal, json.dumps(payload).encode())
    assert error.value.status_code == 400


def test_empty_hex_ids_in_span_links_are_valid() -> None:
    trace_body = b'{"resourceSpans":[{"scopeSpans":[{"spans":[{"links":[{"traceId":"","spanId":""}]}]}]}]}'
    assert parse_export(TelemetrySignal.TRACES, trace_body).item_count == 1


def test_ids_in_exemplars_use_descriptor_validation() -> None:
    body = b'{"resourceMetrics":[{"scopeMetrics":[{"metrics":[{"gauge":{"dataPoints":[{"asInt":"1","exemplars":[{"traceId":"bad","spanId":"bad"}]}]}}]}]}]}'
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(TelemetrySignal.METRICS, body)
    assert error.value.status_code == 400
