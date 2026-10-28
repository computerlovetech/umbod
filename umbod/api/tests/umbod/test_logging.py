from __future__ import annotations

import json
import logging
import sys
from io import StringIO
from typing import Any

import pytest

from umbod.logging import OpenTelemetryJsonFormatter, configure_logging, log_safe_exception


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


def test_safe_exception_log_exports_frames_without_sensitive_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    try:
        raise RuntimeError("raw-token-sentinel")
    except RuntimeError as error:
        log_safe_exception(logging.getLogger("test.safe"), "Instrumentation failed", error)

    attributes = _payload(caplog.records[-1], "test-service")["attributes"]

    assert attributes["exception.type"] == "RuntimeError"
    assert "test_safe_exception_log_exports_frames" in attributes["exception.stacktrace"]
    assert "raw-token-sentinel" not in json.dumps(attributes)
    assert "exception.message" not in attributes
    assert attributes["mcp.failure.origin"] == "internal"


def test_configure_logging_is_idempotent_and_routes_framework_loggers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    framework_names = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastmcp", "mcp")
    framework_states = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate)
        for name in framework_names
    }
    framework_logger = logging.getLogger("uvicorn.access")
    original_framework_level = framework_logger.level
    original_framework_disabled = framework_logger.disabled
    framework_handler = logging.StreamHandler(StringIO())
    try:
        for handler in original_handlers:
            root.removeHandler(handler)
        framework_logger.addHandler(framework_handler)
        framework_logger.setLevel(logging.DEBUG)
        framework_logger.disabled = False

        configure_logging("first", "INFO")
        configure_logging("second", "DEBUG")

        message = "framework-debug-delivery-after-reconfiguration"
        framework_logger.debug(message)
        records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        matching_records = [record for record in records if record["body"] == message]
        assert len(matching_records) == 1
        assert matching_records[0]["resource"] == {"service.name": "second"}
        assert matching_records[0]["severity_text"] == "DEBUG"
        assert matching_records[0]["severity_number"] == 5
        assert root.level == logging.DEBUG
        assert framework_logger.handlers == []
        assert framework_logger.propagate is True
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            if handler not in original_handlers:
                handler.close()
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)
        for name, (handlers, propagate) in framework_states.items():
            logger = logging.getLogger(name)
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
            for handler in handlers:
                logger.addHandler(handler)
            logger.propagate = propagate
        framework_logger.setLevel(original_framework_level)
        framework_logger.disabled = original_framework_disabled
        framework_handler.close()
