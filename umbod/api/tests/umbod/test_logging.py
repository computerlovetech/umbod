from __future__ import annotations

import json
import logging
import sys
from io import StringIO
from typing import Any

import pytest

from umbod.logging import OpenTelemetryJsonFormatter, configure_logging


def _payload(record: logging.LogRecord, service_name: str) -> dict[str, Any]:
    return json.loads(OpenTelemetryJsonFormatter(service_name).format(record))


@pytest.mark.parametrize(
    ("level", "severity_text", "severity_number"),
    [
        (logging.DEBUG, "DEBUG", 5),
        (logging.INFO, "INFO", 9),
        (logging.WARNING, "WARNING", 13),
        (logging.ERROR, "ERROR", 17),
        (logging.CRITICAL, "CRITICAL", 21),
    ],
)
def test_formatter_emits_opentelemetry_envelope(
    level: int, severity_text: str, severity_number: int
) -> None:
    record = logging.LogRecord("test", level, "", 0, "message", (), None)
    record.structured_attributes = {"explicit": {"value": object()}}
    record.trace_id = "trace"
    record.span_id = "span"

    payload = _payload(record, "test-service")

    assert isinstance(payload["timestamp"], int)
    assert isinstance(payload["observed_timestamp"], int)
    assert payload["severity_text"] == severity_text
    assert payload["severity_number"] == severity_number
    assert payload["body"] == "message"
    assert payload["resource"] == {"service.name": "test-service"}
    assert payload["attributes"]["explicit"]["value"].startswith("<object object")
    assert payload["trace_id"] == "trace"
    assert payload["span_id"] == "span"


def test_formatter_maps_exception_attributes() -> None:
    try:
        raise ValueError("invalid")
    except ValueError:
        exception_info = sys.exc_info()
    record = logging.LogRecord("test", logging.ERROR, "", 0, "failed", (), exception_info)

    attributes = _payload(record, "test-service")["attributes"]

    assert attributes["exception.type"] == "ValueError"
    assert attributes["exception.message"] == "invalid"
    assert "ValueError: invalid" in attributes["exception.stacktrace"]


def test_configure_logging_is_idempotent_and_routes_framework_loggers() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    framework_names = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastmcp", "mcp")
    framework_states = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate)
        for name in framework_names
    }
    framework_logger = logging.getLogger("uvicorn.access")
    try:
        framework_logger.addHandler(logging.StreamHandler(StringIO()))

        configure_logging("first", "INFO")
        configure_logging("second", "DEBUG")

        owned_handlers = [
            handler
            for handler in root.handlers
            if getattr(handler, "_umbod_otel_stdout_handler", False)
        ]
        assert len(owned_handlers) == 1
        assert root.level == logging.DEBUG
        assert framework_logger.handlers == []
        assert framework_logger.propagate is True
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)
        for name, (handlers, propagate) in framework_states.items():
            logger = logging.getLogger(name)
            logger.handlers = handlers
            logger.propagate = propagate
