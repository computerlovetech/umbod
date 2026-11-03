import base64

import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from pydantic import JsonValue

from umbod.core.telemetry import TelemetrySignal
from umbod.rest.telemetry.errors import TelemetryHttpError
from umbod.rest.telemetry.validation import parse_protobuf_export


@pytest.mark.parametrize("signal", list(TelemetrySignal))
def test_zero_byte_protobuf_is_a_valid_empty_export(signal: TelemetrySignal) -> None:
    batch = parse_protobuf_export(signal, b"")
    assert batch.signal == signal
    assert batch.item_count == 0
    assert batch.payload == {}


@pytest.mark.parametrize("signal", list(TelemetrySignal))
@pytest.mark.parametrize("body", [b"\xff", b"\x0a\x05x", b"\x00", b"\x0a\x01\xff"])
def test_malformed_protobuf_is_rejected_with_safe_error(
    signal: TelemetrySignal, body: bytes
) -> None:
    with pytest.raises(TelemetryHttpError) as error:
        parse_protobuf_export(signal, body)
    assert error.value.status_code == 400
    assert error.value.message == "Invalid OTLP protobuf request"


@pytest.mark.parametrize("signal", list(TelemetrySignal))
def test_unknown_protobuf_fields_are_ignored(signal: TelemetrySignal) -> None:
    batch = parse_protobuf_export(signal, b"\xa2\x06\x07private")
    assert batch.item_count == 0
    assert batch.payload == {}


def test_logs_convert_identifiers_enums_and_unsigned_int64() -> None:
    request = ExportLogsServiceRequest()
    record = request.resource_logs.add().scope_logs.add().log_records.add()
    record.trace_id = bytes.fromhex("ab" * 16)
    record.span_id = bytes.fromhex("cd" * 8)
    record.severity_number = 12345
    record.time_unix_nano = 2**64 - 1
    batch = parse_protobuf_export(TelemetrySignal.LOGS, request.SerializeToString())
    assert batch.item_count == 1
    assert batch.payload == {
        "resourceLogs": [
            {
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "traceId": "ab" * 16,
                                "spanId": "cd" * 8,
                                "severityNumber": 12345,
                                "timeUnixNano": str(2**64 - 1),
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_trace_links_and_parent_ids_convert_to_hex_at_every_depth() -> None:
    request = ExportTraceServiceRequest()
    span = request.resource_spans.add().scope_spans.add().spans.add()
    span.trace_id = b"\xab" * 16
    span.span_id = b"\xcd" * 8
    span.parent_span_id = b"\xef" * 8
    span.kind = 12345
    span.status.code = 12345
    span.links.add(trace_id=b"\x12" * 16, span_id=b"\x34" * 8)
    batch = parse_protobuf_export(TelemetrySignal.TRACES, request.SerializeToString())
    assert batch.item_count == 1
    assert batch.payload == {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "ab" * 16,
                                "spanId": "cd" * 8,
                                "parentSpanId": "ef" * 8,
                                "kind": 12345,
                                "status": {"code": 12345},
                                "links": [{"traceId": "12" * 16, "spanId": "34" * 8}],
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_metric_exemplar_ids_and_signed_int64_convert_without_loss() -> None:
    request = ExportMetricsServiceRequest()
    metric = (
        request.resource_metrics.add().scope_metrics.add().metrics.add(name="tokens")
    )
    metric.sum.aggregation_temporality = 12345
    point = metric.sum.data_points.add(as_int=-(2**63))
    point.exemplars.add(trace_id=b"\xab" * 16, span_id=b"\xcd" * 8, as_int=2**63 - 1)
    batch = parse_protobuf_export(TelemetrySignal.METRICS, request.SerializeToString())
    assert batch.item_count == 1
    assert batch.payload == {
        "resourceMetrics": [
            {
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "tokens",
                                "sum": {
                                    "aggregationTemporality": 12345,
                                    "dataPoints": [
                                        {
                                            "asInt": str(-(2**63)),
                                            "exemplars": [
                                                {
                                                    "traceId": "ab" * 16,
                                                    "spanId": "cd" * 8,
                                                    "asInt": str(2**63 - 1),
                                                }
                                            ],
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                ]
            }
        ]
    }


@pytest.mark.parametrize("location", ["log", "span", "parent", "link", "exemplar"])
@pytest.mark.parametrize("width", [1, 7, 9, 15, 17])
def test_incorrect_identifier_widths_are_rejected(location: str, width: int) -> None:
    if location == "log":
        request = ExportLogsServiceRequest()
        request.resource_logs.add().scope_logs.add().log_records.add(
            trace_id=b"x" * width
        )
        signal = TelemetrySignal.LOGS
    elif location == "exemplar":
        request = ExportMetricsServiceRequest()
        point = (
            request.resource_metrics.add()
            .scope_metrics.add()
            .metrics.add()
            .gauge.data_points.add()
        )
        point.exemplars.add(span_id=b"x" * width)
        signal = TelemetrySignal.METRICS
    else:
        request = ExportTraceServiceRequest()
        span = request.resource_spans.add().scope_spans.add().spans.add()
        if location == "span":
            span.span_id = b"x" * width
        elif location == "parent":
            span.parent_span_id = b"x" * width
        else:
            span.links.add(trace_id=b"x" * width)
        signal = TelemetrySignal.TRACES
    with pytest.raises(TelemetryHttpError) as error:
        parse_protobuf_export(signal, request.SerializeToString())
    assert error.value.status_code == 400


@pytest.mark.parametrize(
    "value,expected",
    [
        (
            AnyValue(bytes_value=b"\x00\xff\x80"),
            {"bytesValue": base64.b64encode(b"\x00\xff\x80").decode()},
        ),
        (AnyValue(int_value=-(2**63)), {"intValue": str(-(2**63))}),
        (AnyValue(double_value=float("nan")), {"doubleValue": "NaN"}),
        (AnyValue(double_value=float("inf")), {"doubleValue": "Infinity"}),
        (AnyValue(double_value=float("-inf")), {"doubleValue": "-Infinity"}),
    ],
)
def test_anyvalue_bytes_int64_and_nonfinite_doubles_use_protojson_representation(
    value: AnyValue, expected: dict[str, JsonValue]
) -> None:
    request = ExportLogsServiceRequest()
    request.resource_logs.add().scope_logs.add().log_records.add().body.CopyFrom(value)
    batch = parse_protobuf_export(TelemetrySignal.LOGS, request.SerializeToString())
    assert batch.payload == {
        "resourceLogs": [{"scopeLogs": [{"logRecords": [{"body": expected}]}]}]
    }


@pytest.mark.parametrize(
    "value,expected",
    [(float("nan"), "NaN"), (float("inf"), "Infinity"), (float("-inf"), "-Infinity")],
)
def test_metric_nonfinite_doubles_use_protojson_strings(
    value: float, expected: str
) -> None:
    request = ExportMetricsServiceRequest()
    request.resource_metrics.add().scope_metrics.add().metrics.add().gauge.data_points.add(
        as_double=value
    )
    batch = parse_protobuf_export(TelemetrySignal.METRICS, request.SerializeToString())
    assert batch.payload == {
        "resourceMetrics": [
            {
                "scopeMetrics": [
                    {"metrics": [{"gauge": {"dataPoints": [{"asDouble": expected}]}}]}
                ]
            }
        ]
    }
