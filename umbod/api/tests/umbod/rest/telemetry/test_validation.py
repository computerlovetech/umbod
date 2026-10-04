import json

import pytest
from pydantic import JsonValue

from umbod.core.telemetry import TelemetrySignal
from umbod.rest.telemetry.errors import TelemetryHttpError
from umbod.rest.telemetry.validation import parse_export


def export_payload(
    signal: TelemetrySignal, records: list[dict[str, JsonValue]]
) -> dict[str, JsonValue]:
    names = {
        TelemetrySignal.LOGS: ("resourceLogs", "scopeLogs", "logRecords"),
        TelemetrySignal.TRACES: ("resourceSpans", "scopeSpans", "spans"),
        TelemetrySignal.METRICS: ("resourceMetrics", "scopeMetrics", "metrics"),
    }
    resource, scope, items = names[signal]
    return {resource: [{scope: [{items: records}]}]}


def encode(payload: dict[str, JsonValue]) -> bytes:
    return json.dumps(payload).encode()


@pytest.mark.parametrize("signal", list(TelemetrySignal))
def test_empty_export_has_no_items(signal: TelemetrySignal) -> None:
    batch = parse_export(signal, b"{}")
    assert batch.item_count == 0
    assert batch.payload == {}


@pytest.mark.parametrize("signal", list(TelemetrySignal))
def test_unknown_fields_are_preserved_but_not_counted(signal: TelemetrySignal) -> None:
    payload = {"futureResource": {"spans": [{}], "logRecords": [{}], "metrics": [{}]}}
    batch = parse_export(signal, encode(payload))
    assert batch.item_count == 0
    assert batch.payload == payload


@pytest.mark.parametrize(
    "signal,record,expected",
    [
        (
            TelemetrySignal.LOGS,
            {
                "body": {"stringValue": "hello"},
                "severityNumber": 9,
                "timeUnixNano": "18446744073709551615",
            },
            1,
        ),
        (
            TelemetrySignal.TRACES,
            {
                "name": "operation",
                "kind": 2,
                "traceId": "aB" * 16,
                "spanId": "Cd" * 8,
                "parentSpanId": "Ef" * 8,
                "startTimeUnixNano": "1700000000000000001",
                "endTimeUnixNano": 1700000000000000002,
            },
            1,
        ),
        (
            TelemetrySignal.METRICS,
            {
                "name": "requests",
                "sum": {
                    "aggregationTemporality": 2,
                    "isMonotonic": True,
                    "dataPoints": [
                        {
                            "asInt": "9223372036854775807",
                            "timeUnixNano": "1700000000000000001",
                        }
                    ],
                },
            },
            1,
        ),
    ],
)
def test_multiple_resources_and_scopes_preserve_complete_payload(
    signal: TelemetrySignal, record: dict[str, JsonValue], expected: int
) -> None:
    payload = export_payload(signal, [record])
    resource_name = next(iter(payload))
    resources = payload[resource_name]
    assert isinstance(resources, list)
    resource = resources[0]
    assert isinstance(resource, dict)
    resource["resource"] = {
        "attributes": [
            {"key": "service.name", "value": {"stringValue": "source-service"}}
        ],
        "droppedAttributesCount": 1,
    }
    resource["schemaUrl"] = "https://source/schema"
    scope_name = next(key for key in resource if key.startswith("scope"))
    scopes = resource[scope_name]
    assert isinstance(scopes, list)
    scope = scopes[0]
    assert isinstance(scope, dict)
    scope["scope"] = {
        "name": "instrumentation",
        "version": "1",
        "attributes": [{"key": "enabled", "value": {"boolValue": True}}],
    }
    scope["schemaUrl"] = "https://scope/schema"
    scope["futureField"] = {"nested": [None, 1, True]}
    scopes.append(scope)
    resources.append(resource)
    batch = parse_export(signal, encode(payload))
    assert batch.item_count == expected * 4
    assert batch.payload == payload


@pytest.mark.parametrize(
    "value",
    [
        {"stringValue": "source"},
        {"boolValue": False},
        {"intValue": "-9223372036854775808"},
        {"doubleValue": 1.25},
        {"bytesValue": "YWJj"},
        {"arrayValue": {"values": [{"intValue": "12"}, {"boolValue": True}]}},
        {
            "kvlistValue": {
                "values": [{"key": "nested", "value": {"stringValue": "kept"}}]
            }
        },
    ],
)
def test_logs_accept_all_typed_any_values(value: dict[str, JsonValue]) -> None:
    payload = export_payload(
        TelemetrySignal.LOGS,
        [{"body": value, "attributes": [{"key": "typed", "value": value}]}],
    )
    batch = parse_export(TelemetrySignal.LOGS, encode(payload))
    assert batch.payload == payload
    assert batch.item_count == 1


@pytest.mark.parametrize(
    "variant,data",
    [
        ("gauge", {"dataPoints": [{"asDouble": 1.5}, {"asInt": 3}]}),
        ("sum", {"aggregationTemporality": 1, "dataPoints": [{"asInt": "4"}]}),
        (
            "histogram",
            {
                "aggregationTemporality": 2,
                "dataPoints": [
                    {
                        "count": "3",
                        "sum": 4.0,
                        "bucketCounts": ["1", "2"],
                        "explicitBounds": [1.0],
                    }
                ],
            },
        ),
        (
            "exponentialHistogram",
            {
                "aggregationTemporality": 2,
                "dataPoints": [
                    {
                        "count": 3,
                        "scale": -1,
                        "positive": {"offset": 0, "bucketCounts": ["3"]},
                    }
                ],
            },
        ),
        (
            "summary",
            {
                "dataPoints": [
                    {
                        "count": "3",
                        "sum": 4.0,
                        "quantileValues": [{"quantile": 0.5, "value": 1.0}],
                    }
                ]
            },
        ),
    ],
)
def test_metrics_count_all_supported_datapoint_variants(
    variant: str, data: dict[str, JsonValue]
) -> None:
    payload = export_payload(
        TelemetrySignal.METRICS,
        [
            {"name": variant, variant: data},
            {"name": "unset", "futureData": {"dataPoints": [{}]}},
        ],
    )
    batch = parse_export(TelemetrySignal.METRICS, encode(payload))
    points = data["dataPoints"]
    assert isinstance(points, list)
    assert batch.item_count == len(points)
    assert batch.payload == payload


@pytest.mark.parametrize(
    "signal,record",
    [
        (TelemetrySignal.LOGS, {"severityNumber": "SEVERITY_NUMBER_INFO"}),
        (TelemetrySignal.LOGS, {"severityNumber": "9"}),
        (TelemetrySignal.LOGS, {"severityNumber": True}),
        (TelemetrySignal.TRACES, {"kind": "SPAN_KIND_SERVER"}),
        (TelemetrySignal.TRACES, {"status": {"code": "STATUS_CODE_OK"}}),
        (
            TelemetrySignal.METRICS,
            {"sum": {"aggregationTemporality": "AGGREGATION_TEMPORALITY_DELTA"}},
        ),
        (TelemetrySignal.LOGS, {"time_unix_nano": "1"}),
        (TelemetrySignal.TRACES, {"parent_span_id": "ab" * 8}),
        (TelemetrySignal.METRICS, {"sum": {"data_points": []}}),
        (
            TelemetrySignal.LOGS,
            {"body": {"stringValue": "private payload", "intValue": "1"}},
        ),
        (TelemetrySignal.LOGS, {"body": {"intValue": "9223372036854775808"}}),
        (TelemetrySignal.LOGS, {"timeUnixNano": "18446744073709551616"}),
        (TelemetrySignal.TRACES, {"attributes": "wrong"}),
        (TelemetrySignal.METRICS, {"gauge": {}, "sum": {}}),
        (
            TelemetrySignal.METRICS,
            {"sum": {"dataPoints": [{"asInt": "-9223372036854775809"}]}},
        ),
    ],
)
def test_schema_errors_reject_entire_batch_with_safe_message(
    signal: TelemetrySignal, record: dict[str, JsonValue]
) -> None:
    payload = export_payload(signal, [{}, record])
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(signal, encode(payload))
    assert error.value.status_code == 400
    assert error.value.message == "Invalid OTLP JSON request"


@pytest.mark.parametrize("field", ["traceId", "spanId", "parentSpanId"])
@pytest.mark.parametrize("value", ["bad", "z" * 32, "YWJj", 123])
def test_trace_ids_require_hex_width(field: str, value: JsonValue) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(
            TelemetrySignal.TRACES,
            encode(export_payload(TelemetrySignal.TRACES, [{field: value}])),
        )
    assert error.value.status_code == 400


@pytest.mark.parametrize("signal", [TelemetrySignal.LOGS, TelemetrySignal.TRACES])
@pytest.mark.parametrize("trace_id,span_id", [("", ""), ("Ab" * 16, "cD" * 8)])
def test_log_and_trace_hex_ids_are_preserved(
    signal: TelemetrySignal, trace_id: str, span_id: str
) -> None:
    payload = export_payload(signal, [{"traceId": trace_id, "spanId": span_id}])
    assert parse_export(signal, encode(payload)).payload == payload


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"{",
        b"\xff",
        b"[]",
        b"null",
        b"1",
        b'"text"',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":-Infinity}',
        b'{"x":1e999}',
        b'{"x":1,"x":2}',
        b'{"x":{"y":1,"y":2}}',
    ],
)
def test_invalid_json_rejected(body: bytes) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(TelemetrySignal.LOGS, body)
    assert error.value.status_code == 400


@pytest.mark.parametrize("depth", [110, 1100])
def test_excessive_json_nesting_is_safe(depth: int) -> None:
    body = b'{"unknown":' + b"[" * depth + b"0" + b"]" * depth + b"}"
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(TelemetrySignal.LOGS, body)
    assert error.value.status_code == 400


def test_root_recognized_snake_case_is_rejected() -> None:
    with pytest.raises(TelemetryHttpError):
        parse_export(TelemetrySignal.LOGS, b'{"resource_logs":[]}')


@pytest.mark.parametrize(
    "signal,record",
    [
        (
            TelemetrySignal.TRACES,
            {
                "traceId": None,
                "spanId": None,
                "parentSpanId": None,
                "kind": None,
                "status": None,
                "links": [{"traceId": None, "spanId": None}],
            },
        ),
        (
            TelemetrySignal.METRICS,
            {
                "sum": {
                    "aggregationTemporality": None,
                    "isMonotonic": None,
                    "dataPoints": [
                        {
                            "asDouble": None,
                            "asInt": "1",
                            "exemplars": [{"traceId": None, "spanId": None}],
                        }
                    ],
                }
            },
        ),
        (
            TelemetrySignal.METRICS,
            {
                "histogram": {
                    "dataPoints": [
                        {
                            "count": None,
                            "sum": None,
                            "bucketCounts": None,
                            "explicitBounds": None,
                        }
                    ]
                }
            },
        ),
    ],
)
def test_null_trace_and_metric_fields_preserve_source(
    signal: TelemetrySignal, record: dict[str, JsonValue]
) -> None:
    payload = export_payload(signal, [record])
    batch = parse_export(signal, encode(payload))
    assert batch.item_count == 1
    assert batch.payload == payload


@pytest.mark.parametrize(
    "value",
    ["", "YQ==", "YQ", "YWI=", "YWI", "YWJj", "+/8=", "+/8", "-_8=", "-_8"],
)
def test_anyvalue_accepts_protojson_base64_without_changing_source(value: str) -> None:
    payload = export_payload(TelemetrySignal.LOGS, [{"body": {"bytesValue": value}}])
    assert parse_export(TelemetrySignal.LOGS, encode(payload)).payload == payload


@pytest.mark.parametrize(
    "value",
    ["!", "Y", "YQ=", "YQ===", "YWJj=", "YWI==", "=YQ", "Y=Q=", "Y Q==", "é", 1, True],
)
def test_anyvalue_rejects_invalid_base64(value: JsonValue) -> None:
    payload = export_payload(TelemetrySignal.LOGS, [{"body": {"bytesValue": value}}])
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(TelemetrySignal.LOGS, encode(payload))
    assert error.value.status_code == 400


@pytest.mark.parametrize(
    "value",
    [
        {"doubleValue": "1e2"},
        {"doubleValue": "1.25"},
        {"doubleValue": "NaN"},
        {"doubleValue": "Infinity"},
        {"doubleValue": "-Infinity"},
        {"intValue": "1e2"},
        {"intValue": "1.0"},
    ],
)
def test_numeric_strings_keep_protobuf_parser_syntax(
    value: dict[str, JsonValue],
) -> None:
    payload = export_payload(TelemetrySignal.LOGS, [{"body": value}])
    assert parse_export(TelemetrySignal.LOGS, encode(payload)).payload == payload


@pytest.mark.parametrize(
    "signal,record",
    [
        (TelemetrySignal.LOGS, {"body": {"doubleValue": True}}),
        (TelemetrySignal.LOGS, {"body": {"intValue": False}}),
        (TelemetrySignal.LOGS, {"severityNumber": True}),
        (TelemetrySignal.LOGS, {"timeUnixNano": False}),
        (TelemetrySignal.LOGS, {"droppedAttributesCount": True}),
        (TelemetrySignal.METRICS, {"gauge": {"dataPoints": [{"asDouble": True}]}}),
        (
            TelemetrySignal.METRICS,
            {"histogram": {"dataPoints": [{"bucketCounts": [True]}]}},
        ),
        (
            TelemetrySignal.METRICS,
            {"histogram": {"dataPoints": [{"explicitBounds": [False]}]}},
        ),
    ],
)
def test_boolean_values_are_not_numeric_scalars(
    signal: TelemetrySignal, record: dict[str, JsonValue]
) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        parse_export(signal, encode(export_payload(signal, [record])))
    assert error.value.status_code == 400
