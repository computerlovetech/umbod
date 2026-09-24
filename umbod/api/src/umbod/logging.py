from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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
) | {"message", "asctime", "structured_attributes", "trace_id", "span_id"}


@dataclass(frozen=True)
class StructuredLogRecord:
    body: str
    severity_text: str
    attributes: Mapping[str, Any]
    trace_id: str | None
    span_id: str | None


class OpenTelemetryJsonFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        severity_text = record.levelname.upper()
        attributes = {
            "logger.name": record.name,
            **_normalize_mapping(
                {
                    key: value
                    for key, value in record.__dict__.items()
                    if key not in _STANDARD_LOG_RECORD_KEYS
                }
            ),
            **_normalize_mapping(getattr(record, "structured_attributes", {})),
        }
        if record.exc_info is not None:
            exception_type = record.exc_info[0]
            exception_value = record.exc_info[1]
            attributes.update(
                {
                    "exception.type": exception_type.__name__ if exception_type else "Exception",
                    "exception.message": str(exception_value),
                    "exception.stacktrace": "".join(traceback.format_exception(*record.exc_info)),
                }
            )
        payload: dict[str, Any] = {
            "timestamp": int(record.created * 1_000_000_000),
            "observed_timestamp": time.time_ns(),
            "severity_text": severity_text,
            "severity_number": _SEVERITY_NUMBERS.get(severity_text, record.levelno),
            "body": record.getMessage(),
            "attributes": attributes,
            "resource": {"service.name": self._service_name},
        }
        trace_id = getattr(record, "trace_id", None)
        span_id = getattr(record, "span_id", None)
        if trace_id is not None:
            payload["trace_id"] = str(trace_id)
        if span_id is not None:
            payload["span_id"] = str(span_id)
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
        handler = logging.StreamHandler(sys.stdout)
        setattr(handler, _HANDLER_MARKER, True)
        handler.setFormatter(OpenTelemetryJsonFormatter(service_name))
        root.addHandler(handler)
    root.setLevel(level.upper())
    for logger_name in _FRAMEWORK_LOGGERS:
        framework_logger = logging.getLogger(logger_name)
        framework_logger.handlers.clear()
        framework_logger.propagate = True


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


def _normalize_mapping(values: Any) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        return {}
    return {str(key): _normalize_value(value) for key, value in values.items()}


def _normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return _normalize_mapping(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_normalize_value(item) for item in value]
    return str(value)
