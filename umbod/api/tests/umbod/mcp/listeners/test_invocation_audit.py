from __future__ import annotations

import pytest

from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.logging import (
    McpAuditActivityType,
    McpAuditEvent,
    McpAuditEventSink,
    McpAuditFailureCategory,
    McpAuditOutcome,
    McpAuditRecorder,
)
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink, McpToolInvocationLogSink
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.signals import (
    McpInteractionType,
    McpInvocationActor,
    McpInvocationCorrelation,
    McpSignals,
    McpToolIdentity,
    McpToolInvocationCompleted,
    McpToolInvocationFailed,
    McpToolInvocationFailureCategory,
    McpToolInvocationOutcome,
    McpToolInvocationStarted,
    McpToolInvocationSucceeded,
)

_CORRELATION = McpInvocationCorrelation(trace_id="trace-1", span_id="span-1")


class RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list[McpAuditEvent] = []

    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        self.events.append(event)


class FailingInvocationLogSink:
    def record_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        raise RuntimeError("sink failed")


class FailingAuditSink:
    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        raise RuntimeError("audit failed")


def _completed(
    failure_category: McpToolInvocationFailureCategory | None,
    correlation: McpInvocationCorrelation | None,
) -> McpToolInvocationCompleted:
    started = McpToolInvocationStarted(
        interaction_type=McpInteractionType.TOOL_INVOCATION,
        tool=McpToolIdentity(
            tool_name="slack_search_messages",
            connector_id="slack",
            connector_name="Slack Workspace",
            operation_name="search_messages",
        ),
        actor=McpInvocationActor(
            authenticated_user_id="user@example.com", agent_client_id="claude", session_id="s1"
        ),
        started_at_unix_nano=123,
        correlation=correlation,
    )
    if failure_category is not None:
        return McpToolInvocationFailed(
            started=started, duration_ms=1.5, failure_category=failure_category
        )
    return McpToolInvocationSucceeded(started=started, duration_ms=1.5)


def _in_memory_sink() -> InMemoryMcpToolInvocationLogSink:
    return InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter())


def _signals(log_sink: McpToolInvocationLogSink, audit_sink: McpAuditEventSink) -> McpSignals:
    return create_mcp_signals(
        log_sink,
        InMemoryMcpMetricsRecorder(),
        McpAuditRecorder(audit_sink, "umbod"),
    )


def test_registered_logging_receiver_records_completed_event_to_sink() -> None:
    sink = _in_memory_sink()
    signals = _signals(sink, RecordingAuditSink())

    signals.invocation_completed.send(_completed(None, _CORRELATION))

    record = sink.invocation_records()[0]
    assert record.attributes["mcp.tool.name"] == "slack_search_messages"
    assert record.attributes["mcp.invocation.outcome"] == McpToolInvocationOutcome.SUCCESS


def test_registered_audit_receiver_records_success_invocation_details() -> None:
    audit_sink = RecordingAuditSink()
    signals = _signals(_in_memory_sink(), audit_sink)

    signals.invocation_completed.send(_completed(None, _CORRELATION))

    event = audit_sink.events[0]
    assert event.activity_type == McpAuditActivityType.TOOL_INVOCATION
    assert event.outcome == McpAuditOutcome.SUCCESS
    assert event.failure_category is None
    assert event.actor.authenticated_user_id == "user@example.com"
    assert event.actor.anonymous is False
    assert event.client.client_id == "claude"
    assert event.client.session_id == "s1"
    assert event.target.server_name == "umbod"
    assert event.target.tool_name == "slack_search_messages"
    assert event.target.connector_id == "slack"
    assert event.target.connector_name == "Slack Workspace"
    assert event.target.operation_name == "search_messages"
    assert event.occurred_at_unix_nano == 123
    assert event.correlation.trace_id == "trace-1"
    assert event.correlation.span_id == "span-1"


@pytest.mark.parametrize(
    ("invocation_category", "audit_category"),
    [
        (McpToolInvocationFailureCategory.VALIDATION, McpAuditFailureCategory.VALIDATION),
        (McpToolInvocationFailureCategory.AUTHORIZATION, McpAuditFailureCategory.AUTHORIZATION),
        (McpToolInvocationFailureCategory.CONNECTOR_ERROR, McpAuditFailureCategory.CONNECTOR_ERROR),
        (
            McpToolInvocationFailureCategory.UNEXPECTED_ERROR,
            McpAuditFailureCategory.UNEXPECTED_ERROR,
        ),
    ],
)
def test_registered_audit_receiver_maps_failure_category(
    invocation_category: McpToolInvocationFailureCategory,
    audit_category: McpAuditFailureCategory,
) -> None:
    audit_sink = RecordingAuditSink()
    signals = _signals(_in_memory_sink(), audit_sink)

    signals.invocation_completed.send(_completed(invocation_category, _CORRELATION))

    event = audit_sink.events[0]
    assert event.outcome == McpAuditOutcome.FAILURE
    assert event.failure_category == audit_category


def test_registered_audit_receiver_generates_correlation_when_missing() -> None:
    audit_sink = RecordingAuditSink()
    signals = _signals(_in_memory_sink(), audit_sink)

    signals.invocation_completed.send(_completed(None, None))

    assert audit_sink.events[0].correlation.trace_id
    assert audit_sink.events[0].correlation.span_id is None


def test_dispatcher_fans_out_to_all_registered_listeners() -> None:
    sink = _in_memory_sink()
    audit_sink = RecordingAuditSink()
    metrics = InMemoryMcpMetricsRecorder()
    signals = create_mcp_signals(sink, metrics, McpAuditRecorder(audit_sink, "umbod"))

    signals.invocation_completed.send(_completed(None, _CORRELATION))

    assert len(sink.invocation_records()) == 1
    assert len(audit_sink.events) == 1
    assert any(sample.value == 1 for sample in metrics.metric_samples())


def test_dispatcher_failing_receiver_does_not_block_later_receiver() -> None:
    signals = _signals(_in_memory_sink(), RecordingAuditSink())
    received: list[McpToolInvocationCompleted] = []

    def failing_receiver(event: McpToolInvocationCompleted) -> None:
        raise RuntimeError("receiver failed")

    signals.invocation_completed.connect("test.failing", failing_receiver)
    signals.invocation_completed.connect("test.recording", received.append)
    completed = _completed(None, _CORRELATION)

    signals.invocation_completed.send(completed)

    assert received == [completed]


def test_dispatcher_failing_log_sink_does_not_block_audit() -> None:
    audit_sink = RecordingAuditSink()
    signals = _signals(FailingInvocationLogSink(), audit_sink)

    signals.invocation_completed.send(_completed(None, _CORRELATION))

    assert len(audit_sink.events) == 1


def test_dispatcher_failing_audit_sink_does_not_block_later_receiver() -> None:
    sink = _in_memory_sink()
    signals = _signals(sink, FailingAuditSink())
    received: list[McpToolInvocationCompleted] = []
    signals.invocation_completed.connect("test.recording", received.append)
    completed = _completed(None, _CORRELATION)

    signals.invocation_completed.send(completed)

    assert len(sink.invocation_records()) == 1
    assert received == [completed]
