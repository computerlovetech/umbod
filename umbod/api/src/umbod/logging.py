from __future__ import annotations

import json
import logging
import math
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import islice
from typing import Any

from umbod.core.invocation.failure_evidence import InvocationFailureOrigin, exception_evidence
from umbod.core.diagnostics import (
    ApplicationFailure, ApplicationFailureKind, CorrelatedFailureContext,
    SignalFailureContext, capture_application_failure,
)
from umbod.core.signals import Signal
from umbod.core.telemetry.models import TelemetryExport

_SEVERITY_NUMBERS: Mapping[str, int] = {
    "DEBUG": 5,
    "INFO": 9,
    "WARNING": 13,
    "ERROR": 17,
    "CRITICAL": 21,
}
_FRAMEWORK_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastmcp", "mcp")
_HANDLER_MARKER = "_umbod_otel_stdout_handler"
_STANDARD_LOG_RECORD_KEYS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "structured_attributes", "trace_id", "span_id", "_umbod_stdout_delivery", "_umbod_telemetry_export"}


@dataclass(frozen=True)
class StructuredLogRecord:
    body: str
    severity_text: str
    attributes: Mapping[str, Any]
    trace_id: str | None
    span_id: str | None


class StdoutLogDeliveryError(RuntimeError):
    pass


@dataclass
class _StdoutLogDelivery:
    completed: bool


class _StdoutLogHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        delivery = getattr(record, "_umbod_stdout_delivery", None)
        if isinstance(delivery, _StdoutLogDelivery):
            delivery.completed = True

    def handleError(self, record: logging.LogRecord) -> None:
        if isinstance(getattr(record, "_umbod_stdout_delivery", None), _StdoutLogDelivery):
            raise StdoutLogDeliveryError("Stdout logging failed") from None
        sys.stderr.write("Logging delivery failed\n")


class OpenTelemetryJsonFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        severity_text = record.levelname.upper()
        trusted = record.name == "umbod" or record.name.startswith("umbod.")
        attributes = {
            "logger.name": _normalize_value(record.name),
            **_normalize_mapping(
                {
                    key: value
                    for key, value in record.__dict__.items()
                    if trusted and key not in _STANDARD_LOG_RECORD_KEYS
                }
            ),
            **_normalize_mapping(getattr(record, "structured_attributes", {}) if trusted else {}),
        }
        export = getattr(record, "_umbod_telemetry_export", None)
        if record.name == "umbod.structured" and isinstance(export, TelemetryExport):
            serialized_export = export.model_dump(mode="json")
            attributes["telemetry.signal"] = serialized_export["signal"]
            attributes["telemetry.payload"] = serialized_export["payload"]
        attributes.pop("exception.message", None)
        if record.exc_info is not None and isinstance(record.exc_info[1], BaseException):
            evidence = exception_evidence(record.exc_info[1], InvocationFailureOrigin.INTERNAL)
            attributes.update({
                "exception.type": _normalize_value(evidence.exception_type),
                "exception.stacktrace": _bounded_stacktrace(evidence.stacktrace),
            })
        payload: dict[str, Any] = {
            "timestamp": int(record.created * 1_000_000_000),
            "observed_timestamp": time.time_ns(),
            "severity_text": severity_text,
            "severity_number": _SEVERITY_NUMBERS.get(severity_text, record.levelno),
            "body": (
                _normalize_value(record.msg)
                if trusted and type(record.msg) is str and not record.args
                else "Log message omitted"
            ),
            "attributes": attributes,
            "resource": {"service.name": self._service_name},
        }
        trace_id = getattr(record, "trace_id", None)
        span_id = getattr(record, "span_id", None)
        if trusted and type(trace_id) is str:
            payload["trace_id"] = _normalize_value(trace_id)
        if trusted and type(span_id) is str:
            payload["span_id"] = _normalize_value(span_id)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_logging(service_name: str, level: str) -> None:
    root = logging.getLogger()
    owned_handlers = [handler for handler in root.handlers if getattr(handler, _HANDLER_MARKER, False)]
    if owned_handlers:
        handler = owned_handlers[0]
        handler.setFormatter(OpenTelemetryJsonFormatter(service_name))
        for duplicate in owned_handlers[1:]:
            root.removeHandler(duplicate)
    else:
        handler = _StdoutLogHandler(sys.stdout)
        setattr(handler, _HANDLER_MARKER, True)
        handler.setFormatter(OpenTelemetryJsonFormatter(service_name))
        root.addHandler(handler)
    root.setLevel(level.upper())
    for logger_name in _FRAMEWORK_LOGGERS:
        framework_logger = logging.getLogger(logger_name)
        framework_logger.handlers.clear()
        framework_logger.propagate = True


class ApplicationFailureLoggingReceiver:
    def __call__(self, event: ApplicationFailure) -> None:
        extra: dict[str, Any] = {"structured_attributes": dict(event.attributes)}
        if isinstance(event.correlation, CorrelatedFailureContext):
            extra.update(trace_id=event.correlation.trace_id, span_id=event.correlation.span_id)
        logging.getLogger("umbod.application.failure").error(event.kind.value[0], extra=extra)


class LoggingSignalFailureHandler:
    def handles(self, receiver_name: str, error: Exception) -> None:
        event = capture_application_failure(
            ApplicationFailureKind.SIGNAL_RECEIVER, error, SignalFailureContext(receiver_name),
        )
        ApplicationFailureLoggingReceiver()(event)


def create_application_failure_signal() -> Signal[ApplicationFailure]:
    signal = Signal[ApplicationFailure](LoggingSignalFailureHandler())
    signal.connect("application.failure.logging", ApplicationFailureLoggingReceiver())
    return signal


def flush_logging() -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            handler.flush()


def emit_structured_record(structured_record: StructuredLogRecord) -> None:
    target = logging.getLogger("umbod.structured")
    target.log(
        logging.getLevelNamesMapping().get(structured_record.severity_text.upper(), logging.INFO),
        structured_record.body,
        extra={
            "structured_attributes": dict(structured_record.attributes),
            "trace_id": structured_record.trace_id,
            "span_id": structured_record.span_id,
        },
    )


def emit_telemetry_export_to_stdout(batch: TelemetryExport) -> None:
    delivery = _StdoutLogDelivery(completed=False)
    target = logging.getLogger("umbod.structured")
    target.info(
        "Telemetry export received",
        extra={
            "structured_attributes": {"event.name": "umbod.telemetry.export"},
            "_umbod_telemetry_export": batch,
            "_umbod_stdout_delivery": delivery,
        },
    )
    if not delivery.completed:
        raise StdoutLogDeliveryError("Stdout logging is unavailable")


def format_structured_record(
    service_name: str, structured_record: StructuredLogRecord
) -> str:
    level = logging.getLevelNamesMapping().get(
        structured_record.severity_text.upper(), logging.INFO
    )
    record = logging.LogRecord(
        "umbod.structured", level, "", 0, structured_record.body, (), None
    )
    record.structured_attributes = dict(structured_record.attributes)
    record.trace_id = structured_record.trace_id
    record.span_id = structured_record.span_id
    return OpenTelemetryJsonFormatter(service_name).format(record)


_MAX_METADATA_DEPTH = 6
_MAX_METADATA_ITEMS = 64
_MAX_METADATA_NODES = 512
_MAX_METADATA_TEXT = 4096
_OMITTED = "[omitted]"


def _bounded_stacktrace(stacktrace: str) -> str:
    if len(stacktrace) <= _MAX_METADATA_TEXT:
        return stacktrace
    return stacktrace[:_MAX_METADATA_TEXT - 32] + "\n[stacktrace truncated]"


def _normalize_mapping(values: Any) -> dict[str, Any]:
    if type(values) is dict and type(values.get("exception.stacktrace")) is str:
        values = {**values, "exception.stacktrace": _bounded_stacktrace(values["exception.stacktrace"])}
    normalized = _normalize_value(values)
    return normalized if type(normalized) is dict else {}


def _normalize_value(value: Any) -> Any:
    return _normalize_bounded_value(value, 0, [_MAX_METADATA_NODES])


def _normalize_bounded_value(value: Any, depth: int, budget: list[int]) -> Any:
    budget[0] -= 1
    if budget[0] < 0 or depth > _MAX_METADATA_DEPTH:
        return _OMITTED
    if isinstance(value, StrEnum):
        value = str.__str__(value)
    if value is None or type(value) in (bool, int):
        return value if type(value) is not int or value.bit_length() <= 256 else _OMITTED
    if type(value) is float:
        return value if math.isfinite(value) else _OMITTED
    if type(value) is str:
        return value if len(value) <= _MAX_METADATA_TEXT else _OMITTED
    if type(value) is dict:
        result: dict[str, Any] = {}
        for key, item in islice(value.items(), _MAX_METADATA_ITEMS):
            if isinstance(key, StrEnum):
                key = str.__str__(key)
            if type(key) is str and len(key) <= 128:
                result[key] = _normalize_bounded_value(item, depth + 1, budget)
            if budget[0] <= 0:
                break
        if len(value) > len(result):
            result["logging.metadata.omitted"] = True
        return result
    if type(value) in (list, tuple):
        result_items = []
        for item in islice(value, _MAX_METADATA_ITEMS):
            result_items.append(_normalize_bounded_value(item, depth + 1, budget))
            if budget[0] <= 0:
                break
        if len(value) > len(result_items):
            result_items.append(_OMITTED)
        return result_items
    return _OMITTED
