import json
import logging
from typing import Any, Literal
from unittest.mock import Mock

import pytest

from tests.support.application_failures import CapturingApplicationFailures
from umbod.core.capabilities import CapabilityIdentity
from umbod.core.diagnostics import ApplicationFailureKind, PublishingSignalFailureHandler
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.invocation.tools.execution import PreparedToolExecution, ToolExecutionRequest
from umbod.logging import OpenTelemetryJsonFormatter, create_application_failure_signal
from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.logging import McpAuditRecorder, McpToolInvocationLogSink
from umbod.mcp.metrics import McpMetricsRecorder
from umbod.mcp.signals import McpInvocationPublisher, McpToolIdentity, McpToolInvocationCompleted, SignalToolExecutionPipelineFactory


def test_publishing_failure_handler_requires_no_logging(caplog: pytest.LogCaptureFixture) -> None:
    failures = CapturingApplicationFailures()
    handler = PublishingSignalFailureHandler(failures)

    handler.handles("private-receiver", RuntimeError("private-error-token"))

    assert caplog.records == []
    assert len(failures.events) == 1
    event = failures.events[0]
    assert event.kind is ApplicationFailureKind.SIGNAL_RECEIVER
    assert dict(event.attributes)["receiver.name"] == "unrecognized"
    assert "private" not in event.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_receiver", ["logging", "metrics"])
@pytest.mark.parametrize("application_logging", ["healthy", "receiver_failed", "fallback_failed"])
async def test_invocation_receiver_failure_publishes_safe_event_and_preserves_result(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failed_receiver: Literal["logging", "metrics"],
    application_logging: Literal["healthy", "receiver_failed", "fallback_failed"],
) -> None:
    application_failures = create_application_failure_signal()
    failures = CapturingApplicationFailures()
    application_failures.connect("capture", failures.send)
    log = Mock(spec=McpToolInvocationLogSink)
    metrics = Mock(spec=McpMetricsRecorder)
    audit = Mock(spec=McpAuditRecorder)
    failed_method = log.record_invocation_completed if failed_receiver == "logging" else metrics.record_completed_invocation
    failed_method.side_effect = RuntimeError("private-error-token https://private.example/payload")
    signals = create_mcp_signals(log, metrics, audit, application_failures)
    completions: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("capture", completions.append)
    logger = logging.getLogger("umbod.application.failure")
    original_error = logger.error
    attempts: list[dict[str, Any]] = []

    def emit(message: str, *, extra: dict[str, Any]) -> None:
        attempts.append(extra)
        if application_logging == "fallback_failed" or len(attempts) == 1:
            raise RuntimeError("private-logging-token")
        original_error(message, extra=extra)

    if application_logging != "healthy":
        monkeypatch.setattr(logger, "error", emit)

    def result_is_error(result: object) -> bool:
        return False

    pipeline = SignalToolExecutionPipelineFactory(signals, PermitAllConnectorInvocationPolicy()).create(
        "private-connector-name", result_is_error,
    )
    expected_result = object()

    async def operation() -> object:
        return expected_result

    async def prepare() -> PreparedToolExecution[object]:
        return PreparedToolExecution(arguments={}, operation=operation, invocation_arguments={})

    result = await pipeline.execute(
        ToolExecutionRequest(
            identity=CapabilityIdentity(
                connector_kind="openapi", connector_id="private-connector-id",
                capability_kind="tool", capability_key="private-operation",
            ),
            public_tool_name="private-tool", arguments={"token": "private-payload"},
        ),
        prepare,
    )

    assert result is expected_result
    assert len(completions) == 1
    assert len(failures.events) == 1
    event = failures.events[0]
    attributes = dict(event.attributes)
    assert event.kind is ApplicationFailureKind.SIGNAL_RECEIVER
    assert attributes["receiver.name"] == f"mcp.invocation.{failed_receiver}"
    assert attributes["component"] == "signals"
    assert attributes["operation"] == "deliver_signal"
    assert attributes["reason"] == "receiver_failed"
    assert attributes["exception.type"] == "RuntimeError"
    assert "private" not in event.model_dump_json()
    assert not hasattr(event, "error")
    assert not hasattr(event, "traceback")
    log.record_invocation_completed.assert_called_once()
    metrics.record_completed_invocation.assert_called_once()
    audit.record_tool_invocation.assert_called_once()
    if application_logging == "healthy":
        assert len(caplog.records) == 1
        payload = json.loads(OpenTelemetryJsonFormatter("test").format(caplog.records[0]))
        assert payload["body"] == "Signal receiver failed"
        assert payload["attributes"]["receiver.name"] == f"mcp.invocation.{failed_receiver}"
        assert payload["severity_text"] == "ERROR"
        assert "private" not in json.dumps(payload)
    else:
        assert len(attempts) == 2
        assert attempts[1]["structured_attributes"]["receiver.name"] == "application.failure.logging"
        assert "private" not in json.dumps(attempts)
        assert len(caplog.records) == (1 if application_logging == "receiver_failed" else 0)


def test_inventory_receiver_failure_publishes_and_continues_with_remaining_identities(
    caplog: pytest.LogCaptureFixture,
) -> None:
    application_failures = create_application_failure_signal()
    failures = CapturingApplicationFailures()
    application_failures.connect("capture", failures.send)
    log = Mock(spec=McpToolInvocationLogSink)
    metrics = Mock(spec=McpMetricsRecorder)
    audit = Mock(spec=McpAuditRecorder)
    metrics.initialize_invocation.side_effect = [RuntimeError("private-token"), None]
    publisher = McpInvocationPublisher(create_mcp_signals(log, metrics, audit, application_failures))

    publisher.tool_registered(McpToolIdentity("private-first", "private-connector", "private-operation"))
    publisher.tool_registered(McpToolIdentity("private-second", None, None))

    assert metrics.initialize_invocation.call_count == 2
    assert len(failures.events) == 1
    event = failures.events[0]
    assert dict(event.attributes)["receiver.name"] == "mcp.inventory.metrics"
    assert "private" not in event.model_dump_json()
    assert len(caplog.records) == 1
    payload = json.loads(OpenTelemetryJsonFormatter("test").format(caplog.records[0]))
    assert payload["attributes"]["receiver.name"] == "mcp.inventory.metrics"
    assert "private" not in json.dumps(payload)
