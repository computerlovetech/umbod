from __future__ import annotations

import pytest

from umbod.mcp.logging import (
    AuditToolInvocationLogger,
    CompositeConnectorToolInvocationLogger,
    InvocationLogSinkToolInvocationLogger,
    McpAuditEvent,
    McpAuditFailureCategory,
    McpAuditOutcome,
    McpAuditRecorder,
    McpInteractionType,
    McpInvocationActor,
    McpInvocationCorrelation,
    McpToolIdentity,
    McpToolInvocationCompleted,
    McpToolInvocationFailed,
    McpToolInvocationFailureCategory,
    McpToolInvocationOutcome,
    McpToolInvocationStarted,
    McpToolInvocationSucceeded,
    create_default_connector_tool_invocation_logger,
)
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink

_CORRELATION = McpInvocationCorrelation(trace_id="trace-1", span_id="span-1")


class RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list[McpAuditEvent] = []

    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        self.events.append(event)


class FailingInvocationLogger:
    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        raise RuntimeError("logger failed")


class FailingInvocationLogSink:
    def record_invocation_completed(self, event: object) -> None:
        raise RuntimeError("sink failed")


def _completed(
    failure_category: McpToolInvocationFailureCategory | None = None,
    correlation: McpInvocationCorrelation | None = _CORRELATION,
) -> McpToolInvocationCompleted:
    started = McpToolInvocationStarted(
        interaction_type=McpInteractionType.TOOL_INVOCATION,
        tool=McpToolIdentity(
            tool_name="slack_search_messages",
            connector_id="slack",
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


def test_invocation_log_sink_logger_records_completed_event_to_sink() -> None:
    sink = _in_memory_sink()
    logger = InvocationLogSinkToolInvocationLogger(sink)

    logger.record_tool_invocation_completed(_completed())

    record = sink.invocation_records()[0]
    assert record.attributes["mcp.tool.name"] == "slack_search_messages"
    assert record.attributes["mcp.invocation.outcome"] == McpToolInvocationOutcome.SUCCESS


def test_invocation_log_sink_logger_swallows_sink_failures() -> None:
    logger = InvocationLogSinkToolInvocationLogger(FailingInvocationLogSink())

    logger.record_tool_invocation_completed(_completed())


def test_audit_logger_records_success_invocation() -> None:
    audit_sink = RecordingAuditSink()
    logger = AuditToolInvocationLogger(McpAuditRecorder(audit_sink, "umbod"))

    logger.record_tool_invocation_completed(_completed())

    event = audit_sink.events[0]
    assert event.outcome == McpAuditOutcome.SUCCESS
    assert event.failure_category is None
    assert event.target.tool_name == "slack_search_messages"
    assert event.occurred_at_unix_nano == 123
    assert event.correlation.trace_id == "trace-1"


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
def test_audit_logger_maps_failure_category(
    invocation_category: McpToolInvocationFailureCategory,
    audit_category: McpAuditFailureCategory,
) -> None:
    audit_sink = RecordingAuditSink()
    logger = AuditToolInvocationLogger(McpAuditRecorder(audit_sink, "umbod"))

    logger.record_tool_invocation_completed(_completed(failure_category=invocation_category))

    event = audit_sink.events[0]
    assert event.outcome == McpAuditOutcome.FAILURE
    assert event.failure_category == audit_category


def test_audit_logger_generates_correlation_when_missing() -> None:
    audit_sink = RecordingAuditSink()
    logger = AuditToolInvocationLogger(McpAuditRecorder(audit_sink, "umbod"))

    logger.record_tool_invocation_completed(_completed(correlation=None))

    assert audit_sink.events[0].correlation.trace_id


def test_composite_fans_out_to_every_logger() -> None:
    sink = _in_memory_sink()
    audit_sink = RecordingAuditSink()
    logger = CompositeConnectorToolInvocationLogger(
        InvocationLogSinkToolInvocationLogger(sink),
        AuditToolInvocationLogger(McpAuditRecorder(audit_sink, "umbod")),
    )

    logger.record_tool_invocation_completed(_completed())

    assert len(sink.invocation_records()) == 1
    assert len(audit_sink.events) == 1


def test_composite_failing_logger_does_not_block_later_logger() -> None:
    sink = _in_memory_sink()
    logger = CompositeConnectorToolInvocationLogger(
        FailingInvocationLogger(),
        InvocationLogSinkToolInvocationLogger(sink),
    )

    logger.record_tool_invocation_completed(_completed())

    assert len(sink.invocation_records()) == 1


def test_composite_failing_sink_does_not_block_audit() -> None:
    audit_sink = RecordingAuditSink()
    logger = create_default_connector_tool_invocation_logger(
        FailingInvocationLogSink(),
        McpAuditRecorder(audit_sink, "umbod"),
    )

    logger.record_tool_invocation_completed(_completed())

    assert len(audit_sink.events) == 1
