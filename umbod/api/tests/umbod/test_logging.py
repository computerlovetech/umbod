from __future__ import annotations

import json
import logging
import sys
from enum import StrEnum
from hashlib import sha256
from io import StringIO
from typing import Any

import pytest

from umbod.core.diagnostics import (
    ApplicationFailureKind,
    ConnectorLookupFailureContext,
    CorrelatedFailureContext,
    NoFailureContext,
    RestFailureContext,
    SignalFailureContext,
    report_application_failure,
)
from umbod.logging import OpenTelemetryJsonFormatter, configure_logging, create_application_failure_signal


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
    record = logging.LogRecord("umbod.test", level, "", 0, "message", (), None)
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
    assert payload["attributes"]["explicit"]["value"] == "[omitted]"
    assert payload["trace_id"] == "trace"
    assert payload["span_id"] == "span"


def test_formatter_maps_exception_attributes() -> None:
    try:
        raise ValueError("invalid")
    except ValueError:
        exception_info = sys.exc_info()
    record = logging.LogRecord("umbod.test", logging.ERROR, "", 0, "failed", (), exception_info)

    attributes = _payload(record, "test-service")["attributes"]

    assert attributes["exception.type"] == "ValueError"
    assert "exception.message" not in attributes
    assert "ValueError: [message omitted]" in attributes["exception.stacktrace"]


def test_long_sanitized_invocation_stacktrace_retains_bounded_frame_evidence() -> None:
    record = logging.LogRecord("umbod.structured", logging.ERROR, "", 0, "Invocation failed", (), None)
    record.structured_attributes = {
        "exception.type": "RuntimeError",
        "exception.stacktrace": "Traceback (most recent call last):\n" + '  File "adapter.py", line 1, in execute\n' * 200,
    }
    attributes = _payload(record, "test-service")["attributes"]
    assert attributes["exception.type"] == "RuntimeError"
    assert 'File "adapter.py"' in attributes["exception.stacktrace"]
    assert attributes["exception.stacktrace"].endswith("[stacktrace truncated]")
    assert len(attributes["exception.stacktrace"]) <= 4096


def test_safe_exception_log_exports_frames_without_sensitive_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    try:
        raise RuntimeError("raw-token-sentinel")
    except RuntimeError as error:
        report_application_failure(
            create_application_failure_signal(), ApplicationFailureKind.AUDIT_SINK,
            error, NoFailureContext(),
        )

    attributes = _payload(caplog.records[-1], "test-service")["attributes"]

    assert attributes["exception.type"] == "RuntimeError"
    assert "test_safe_exception_log_exports_frames" in attributes["exception.stacktrace"]
    assert "raw-token-sentinel" not in json.dumps(attributes)
    assert "exception.message" not in attributes
    assert attributes["reason"] == "sink_failed"


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
        matching_records = [record for record in records if record["body"] == "Log message omitted"]
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


class SafeTelemetryValue(StrEnum):
    SUCCESS = "success"

    def __str__(self) -> str:
        raise AssertionError("Overridden enum stringification must not run")


def test_safe_string_enum_keys_and_values_are_preserved_without_stringification() -> None:
    record = logging.LogRecord("umbod.test", logging.INFO, "", 0, "event", (), None)
    record.structured_attributes = {SafeTelemetryValue.SUCCESS: SafeTelemetryValue.SUCCESS}

    assert _payload(record, "test")["attributes"]["success"] == "success"


class SensitiveObject:
    def __str__(self) -> str:
        raise AssertionError("Object stringification must not run")

    def __repr__(self) -> str:
        raise AssertionError("Object representation must not run")


@pytest.mark.parametrize("logger_name", ["umbod.test", "uvicorn.error", "third_party"])
def test_formatter_never_stringifies_arbitrary_objects(logger_name: str) -> None:
    value = SensitiveObject()
    record = logging.LogRecord(logger_name, logging.ERROR, "", 0, value, (), None)
    record.structured_attributes = {"object": value, value: "secret-canary"}
    record.trace_id = value
    record.span_id = value

    serialized = OpenTelemetryJsonFormatter("test").format(record)

    assert "secret-canary" not in serialized
    assert json.loads(serialized)["body"] == "Log message omitted"


@pytest.mark.parametrize("logger_name", ["uvicorn.access", "fastmcp.server", "third_party"])
def test_untrusted_messages_and_metadata_are_omitted(logger_name: str) -> None:
    record = logging.LogRecord(logger_name, logging.ERROR, "", 0, "secret-canary", (), None)
    record.structured_attributes = {"url": "secret-canary"}
    record.arbitrary = "secret-canary"
    record.trace_id = "secret-canary"

    serialized = OpenTelemetryJsonFormatter("test").format(record)

    assert "secret-canary" not in serialized
    assert json.loads(serialized)["attributes"] == {"logger.name": logger_name}


def test_message_arguments_are_not_interpolated() -> None:
    record = logging.LogRecord(
        "umbod.test", logging.ERROR, "", 0, "%s", (SensitiveObject(),), None
    )

    assert _payload(record, "test")["body"] == "Log message omitted"


def test_exception_groups_and_chains_export_only_safe_evidence() -> None:
    try:
        try:
            raise ValueError("secret-canary-cause")
        except ValueError as cause:
            raise ExceptionGroup("secret-canary-group", [RuntimeError("secret-canary-child")]) from cause
    except ExceptionGroup:
        exception_info = sys.exc_info()
    record = logging.LogRecord("umbod.test", logging.ERROR, "", 0, "failed", (), exception_info)

    serialized = OpenTelemetryJsonFormatter("test").format(record)
    payload = json.loads(serialized)

    assert "secret-canary" not in serialized
    assert payload["attributes"]["exception.type"] == "ExceptionGroup"
    assert "ValueError" in payload["attributes"]["exception.stacktrace"]
    assert "RuntimeError" in payload["attributes"]["exception.stacktrace"]
    assert "test_exception_groups_and_chains" in payload["attributes"]["exception.stacktrace"]


@pytest.mark.parametrize(
    ("event", "context", "expected"),
    [
        (
            ApplicationFailureKind.CONNECTOR_LOOKUP,
            ConnectorLookupFailureContext("secret-canary-connector", "secret-canary-operation"),
            {
                "connector.id_hash": sha256(b"secret-canary-connector").hexdigest(),
                "operation.name_hash": sha256(b"secret-canary-operation").hexdigest(),
            },
        ),
        (
            ApplicationFailureKind.SIGNAL_RECEIVER,
            SignalFailureContext("secret-canary-receiver"),
            {"receiver.name_hash": sha256(b"secret-canary-receiver").hexdigest()},
        ),
        (
            ApplicationFailureKind.REST_METRICS,
            RestFailureContext("secret-canary-method", 12345, ""),
            {"method": "OTHER", "status_code": 0, "normalized_route": "unmatched"},
        ),
    ],
)
def test_failure_context_retains_only_approved_bounded_fields(
    event: ApplicationFailureKind,
    context: ConnectorLookupFailureContext | SignalFailureContext | RestFailureContext,
    expected: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    report_application_failure(create_application_failure_signal(), event, RuntimeError("secret-canary"), context)

    serialized = OpenTelemetryJsonFormatter("test").format(caplog.records[-1])
    attributes = json.loads(serialized)["attributes"]

    assert "secret-canary" not in serialized
    assert expected.items() <= attributes.items()


class SensitiveException(RuntimeError):
    def __str__(self) -> str:
        raise AssertionError("Exception stringification must not run")


@pytest.mark.parametrize("logger_name", ["umbod.test", "uvicorn.error"])
def test_exception_stringification_is_never_called(logger_name: str) -> None:
    try:
        raise SensitiveException("secret-canary")
    except SensitiveException:
        exception_info = sys.exc_info()
    record = logging.LogRecord(logger_name, logging.ERROR, "", 0, "failed", (), exception_info)

    serialized = OpenTelemetryJsonFormatter("test").format(record)

    assert "secret-canary" not in serialized
    assert "SensitiveException" in json.loads(serialized)["attributes"]["exception.type"]


def _raise_deep_failure(remaining_frames: int) -> None:
    if remaining_frames:
        _raise_deep_failure(remaining_frames - 1)
    raise RuntimeError("secret-canary")


def test_exception_snapshot_size_is_bounded_without_losing_all_frames() -> None:
    try:
        _raise_deep_failure(60)
    except RuntimeError:
        exception_info = sys.exc_info()
    record = logging.LogRecord("umbod.test", logging.ERROR, "", 0, "failed", (), exception_info)

    serialized = OpenTelemetryJsonFormatter("test").format(record)
    stacktrace = json.loads(serialized)["attributes"]["exception.stacktrace"]

    assert "secret-canary" not in serialized
    assert len(stacktrace) <= 4096
    assert "_raise_deep_failure" in stacktrace


def test_metadata_cycles_depth_width_and_text_are_bounded() -> None:
    cycle: dict[str, Any] = {}
    cycle["cycle"] = cycle
    record = logging.LogRecord("umbod.test", logging.INFO, "", 0, "event", (), None)
    record.structured_attributes = {
        "cycle": cycle,
        "wide": list(range(1000)),
        "large": "x" * 10000,
        "unsupported": SensitiveObject(),
        "safe": {"count": 3, "success": True},
    }

    serialized = OpenTelemetryJsonFormatter("test").format(record)
    attributes = json.loads(serialized)["attributes"]

    assert len(serialized) < 5000
    assert attributes["large"] == "[omitted]"
    assert attributes["unsupported"] == "[omitted]"
    assert len(attributes["wide"]) == 65
    assert attributes["safe"] == {"count": 3, "success": True}


@pytest.mark.parametrize("event", list(ApplicationFailureKind))
def test_application_failure_event_exports_fixed_fields_and_safe_evidence(
    event: ApplicationFailureKind, caplog: pytest.LogCaptureFixture,
) -> None:
    try:
        raise RuntimeError("secret-canary")
    except RuntimeError as error:
        report_application_failure(
            create_application_failure_signal(), event, error,
            CorrelatedFailureContext("a" * 32, "b" * 16),
        )

    serialized = OpenTelemetryJsonFormatter("test").format(caplog.records[-1])
    payload = json.loads(serialized)

    assert "secret-canary" not in serialized
    assert payload["body"] == event.value[0]
    assert payload["attributes"]["event.name"] == "application.failure"
    assert payload["attributes"]["component"] == event.value[1]
    assert payload["attributes"]["operation"] == event.value[2]
    assert payload["attributes"]["reason"] == event.value[3]
    assert payload["attributes"]["outcome"] == "failure"
    assert payload["attributes"]["failure.origin"] == "internal"
    assert payload["attributes"]["exception.type"] == "RuntimeError"
    assert payload["trace_id"] == "a" * 32
    assert payload["span_id"] == "b" * 16
