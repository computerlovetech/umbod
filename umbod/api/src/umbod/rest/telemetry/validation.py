import base64
import json
import math
import re

from google.protobuf.descriptor import Descriptor, FieldDescriptor
from google.protobuf.json_format import ParseDict, ParseError
from google.protobuf.message import Message
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from pydantic import JsonValue, ValidationError

from umbod.core.telemetry import TelemetryExport, TelemetrySignal

from .errors import TelemetryHttpError

_REQUEST_TYPES: dict[TelemetrySignal, type[Message]] = {
    TelemetrySignal.LOGS: ExportLogsServiceRequest,
    TelemetrySignal.METRICS: ExportMetricsServiceRequest,
    TelemetrySignal.TRACES: ExportTraceServiceRequest,
}
_ID_LENGTHS = {"traceId": 32, "spanId": 16, "parentSpanId": 16}


def parse_export(signal: TelemetrySignal, body: bytes) -> TelemetryExport:
    try:
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
        if not isinstance(payload, dict):
            raise ValueError
        _check_depth(payload, 0)
        request = _REQUEST_TYPES[signal]()
        normalized = _normalize_message(payload, request.DESCRIPTOR)
        ParseDict(
            normalized, request, ignore_unknown_fields=True, max_recursion_depth=100
        )
        return TelemetryExport(
            signal=signal, payload=payload, item_count=_count_items(request)
        )
    except (
        ValueError,
        UnicodeError,
        ParseError,
        RecursionError,
        ValidationError,
        TypeError,
    ):
        raise TelemetryHttpError(400, "Invalid OTLP JSON request") from None


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(value: str) -> JsonValue:
    raise ValueError


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError
    return result


def _check_depth(value: JsonValue, depth: int) -> None:
    if depth > 100:
        raise ValueError
    if isinstance(value, dict):
        for child in value.values():
            _check_depth(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_depth(child, depth + 1)


def _normalize_message(payload: JsonValue, descriptor: Descriptor) -> JsonValue:
    if not isinstance(payload, dict):
        raise ValueError
    fields = {field.json_name: field for field in descriptor.fields}
    result: dict[str, JsonValue] = {}
    for key, value in payload.items():
        field = fields.get(key)
        if field is None:
            if key in descriptor.fields_by_name:
                raise ValueError
            continue
        if value is None:
            continue
        if field.is_repeated and isinstance(value, list):
            if any(item is None for item in value):
                raise ValueError
            result[key] = [_normalize_field(item, field) for item in value]
        else:
            result[key] = _normalize_field(value, field)
    return result


def _normalize_field(value: JsonValue, field: FieldDescriptor) -> JsonValue:
    if isinstance(value, bool) and field.type != FieldDescriptor.TYPE_BOOL:
        raise ValueError
    if field.type == FieldDescriptor.TYPE_BYTES and field.json_name in _ID_LENGTHS:
        if not isinstance(value, str):
            raise ValueError
        if (
            value
            and re.fullmatch(r"[0-9a-fA-F]{%d}" % _ID_LENGTHS[field.json_name], value)
            is None
        ):
            raise ValueError
        return base64.b64encode(bytes.fromhex(value)).decode("ascii")
    if field.type == FieldDescriptor.TYPE_BYTES:
        _validate_base64(value)
    if field.type == FieldDescriptor.TYPE_ENUM:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError
    if field.type == FieldDescriptor.TYPE_MESSAGE:
        return _normalize_message(value, field.message_type)
    return value


def _validate_base64(value: JsonValue) -> None:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[A-Za-z0-9+/_-]*={0,2}", value) is None
    ):
        raise ValueError
    unpadded = value.rstrip("=")
    padding = len(value) - len(unpadded)
    required_padding = -len(unpadded) % 4
    if required_padding == 3 or (padding and padding != required_padding):
        raise ValueError
    base64.b64decode(unpadded + "=" * required_padding, altchars=b"-_", validate=True)


def _count_items(request: Message) -> int:
    if isinstance(request, ExportLogsServiceRequest):
        return sum(
            len(scope.log_records)
            for resource in request.resource_logs
            for scope in resource.scope_logs
        )
    if isinstance(request, ExportTraceServiceRequest):
        return sum(
            len(scope.spans)
            for resource in request.resource_spans
            for scope in resource.scope_spans
        )
    if isinstance(request, ExportMetricsServiceRequest):
        return sum(
            len(getattr(metric, variant).data_points)
            for resource in request.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if (variant := metric.WhichOneof("data")) is not None
        )
    raise ValueError
