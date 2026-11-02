import json
import logging
from hashlib import sha256
from typing import Any

import pytest
from pydantic import ValidationError

from tests.support.application_failures import CapturingApplicationFailures
from umbod.core.diagnostics import (
    ApplicationFailure,
    ApplicationFailureKind,
    ConnectorLookupFailureContext,
    CorrelatedFailureContext,
    NoFailureContext,
    SignalFailureContext,
    report_application_failure,
)
from umbod.logging import OpenTelemetryJsonFormatter, create_application_failure_signal


def test_subscribers_observe_only_immutable_sanitized_snapshot() -> None:
    failures = CapturingApplicationFailures()
    signal = create_application_failure_signal()
    signal.connect("capture", failures.send)
    error = RuntimeError("token=https://private.example/payload")

    report_application_failure(
        signal, ApplicationFailureKind.CONNECTOR_LOOKUP, error,
        ConnectorLookupFailureContext("private-connector", "private-operation"),
    )
    error.args = ("changed",)

    assert len(failures.events) == 1
    event = failures.events[0]
    attributes = dict(event.attributes)
    assert attributes["connector.id_hash"] == sha256(b"private-connector").hexdigest()
    assert attributes["operation.name_hash"] == sha256(b"private-operation").hexdigest()
    serialized = event.model_dump_json()
    assert "private" not in serialized
    assert "changed" not in serialized
    assert "token=" not in serialized
    assert not hasattr(event, "error")
    assert not hasattr(event, "traceback")
    with pytest.raises(ValidationError, match="frozen"):
        event.kind = ApplicationFailureKind.AUDIT_SINK
    with pytest.raises(TypeError):
        event.attributes[0] = ("reason", "changed")


@pytest.mark.parametrize(
    ("context", "expected_trace", "expected_span"),
    [
        (CorrelatedFailureContext("a" * 32, "b" * 16), "a" * 32, "b" * 16),
        (CorrelatedFailureContext("a" * 32, None), "a" * 32, None),
        (CorrelatedFailureContext("https://private.example", "secret-token"), "[omitted]", "[omitted]"),
    ],
)
def test_correlation_is_sanitized_before_dispatch(
    context: CorrelatedFailureContext, expected_trace: str, expected_span: str | None,
) -> None:
    failures = CapturingApplicationFailures()

    report_application_failure(failures, ApplicationFailureKind.AUDIT_SINK, RuntimeError("secret"), context)

    event = failures.events[0]
    assert event.correlation == CorrelatedFailureContext(expected_trace, expected_span)
    assert "private" not in event.model_dump_json()
    assert "secret" not in event.model_dump_json()


@pytest.mark.parametrize("receiver", ["application.failure.logging", "mcp.invocation.logging", "private-receiver"])
def test_receiver_identifiers_are_allowlisted_or_hashed(receiver: str) -> None:
    failures = CapturingApplicationFailures()

    report_application_failure(
        failures, ApplicationFailureKind.SIGNAL_RECEIVER, RuntimeError("secret"), SignalFailureContext(receiver),
    )

    attributes = dict(failures.events[0].attributes)
    if receiver == "private-receiver":
        assert attributes["receiver.name"] == "unrecognized"
        assert attributes["receiver.name_hash"] == sha256(receiver.encode()).hexdigest()
        assert receiver not in failures.events[0].model_dump_json()
    else:
        assert attributes["receiver.name"] == receiver
        assert "receiver.name_hash" not in attributes


def test_configured_signal_emits_exactly_one_safe_json_record(caplog: pytest.LogCaptureFixture) -> None:
    signal = create_application_failure_signal()

    report_application_failure(signal, ApplicationFailureKind.AUDIT_SINK, RuntimeError("secret"), NoFailureContext())

    assert len(caplog.records) == 1
    payload = json.loads(OpenTelemetryJsonFormatter("test").format(caplog.records[0]))
    assert payload["body"] == "MCP audit logging failed"
    assert payload["severity_text"] == "ERROR"
    assert payload["attributes"]["reason"] == "sink_failed"
    assert "secret" not in json.dumps(payload)


@pytest.mark.parametrize("fallback_fails", [False, True])
def test_logging_receiver_failure_is_terminal_and_other_receivers_continue(
    monkeypatch: pytest.MonkeyPatch, fallback_fails: bool,
) -> None:
    calls: list[dict[str, Any]] = []
    failures = CapturingApplicationFailures()
    signal = create_application_failure_signal()
    signal.connect("capture", failures.send)

    def fail_logging(message: str, *, extra: dict[str, Any]) -> None:
        calls.append(extra)
        if len(calls) == 1 or fallback_fails:
            raise RuntimeError("secret-token")

    monkeypatch.setattr(logging.getLogger("umbod.application.failure"), "error", fail_logging)

    report_application_failure(signal, ApplicationFailureKind.AUDIT_SINK, RuntimeError("secret"), NoFailureContext())

    assert len(calls) == 2
    assert len(failures.events) == 1
    assert calls[1]["structured_attributes"]["reason"] == "receiver_failed"
    assert calls[1]["structured_attributes"]["receiver.name"] == "application.failure.logging"
    assert "secret" not in json.dumps(calls)


def test_custom_receiver_failure_does_not_republish_or_block_subscribers(caplog: pytest.LogCaptureFixture) -> None:
    signal = create_application_failure_signal()
    failures = CapturingApplicationFailures()
    attempted: list[ApplicationFailure] = []

    def fail(event: ApplicationFailure) -> None:
        attempted.append(event)
        raise RuntimeError("secret-token")

    signal.connect("private-receiver", fail)
    signal.connect("capture", failures.send)

    report_application_failure(signal, ApplicationFailureKind.AUDIT_SINK, RuntimeError("secret"), NoFailureContext())

    assert len(attempted) == 1
    assert failures.events == attempted
    assert len(caplog.records) == 2
    payload = json.loads(OpenTelemetryJsonFormatter("test").format(caplog.records[-1]))
    assert payload["attributes"]["receiver.name"] == "unrecognized"
    assert payload["attributes"]["receiver.name_hash"] == sha256(b"private-receiver").hexdigest()
    assert "private-receiver" not in json.dumps(payload)
    assert "secret" not in json.dumps(payload)
