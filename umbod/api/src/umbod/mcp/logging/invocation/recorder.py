from __future__ import annotations

import logging
import uuid

from typing import Protocol

from umbod.mcp.logging.audit.event import (
    McpAuditCorrelation,
    McpAuditFailure,
    McpAuditFailureCategory,
    McpAuditSuccess,
)
from umbod.mcp.logging.audit.identity import audit_identity_from_invocation_actor
from umbod.mcp.logging.audit.recorder import McpAuditRecorder
from umbod.mcp.logging.invocation.event import (
    McpInvocationCorrelation,
    McpToolInvocationCompleted,
    McpToolInvocationFailed,
    McpToolInvocationFailureCategory,
)
from umbod.mcp.logging.invocation.sink import McpToolInvocationLogSink

logger = logging.getLogger(__name__)


class ConnectorToolInvocationLogger(Protocol):
    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None: ...


class InvocationLogSinkToolInvocationLogger:
    def __init__(self, sink: McpToolInvocationLogSink) -> None:
        self._sink = sink

    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        try:
            self._sink.record_invocation_completed(event)
        except Exception:
            logger.error("MCP tool invocation logging failed")


class AuditToolInvocationLogger:
    def __init__(self, recorder: McpAuditRecorder) -> None:
        self._recorder = recorder

    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        started = event.started
        correlation = started.correlation or McpInvocationCorrelation(trace_id=uuid.uuid4().hex)
        self._recorder.record_tool_invocation(
            identity=audit_identity_from_invocation_actor(started.actor),
            target=self._recorder.tool_target(started.tool),
            result=_audit_result(event),
            correlation=McpAuditCorrelation(
                trace_id=correlation.trace_id, span_id=correlation.span_id
            ),
            occurred_at_unix_nano=started.started_at_unix_nano,
        )


class CompositeConnectorToolInvocationLogger:
    def __init__(self, *loggers: ConnectorToolInvocationLogger) -> None:
        self._loggers = loggers

    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        for child in self._loggers:
            try:
                child.record_tool_invocation_completed(event)
            except Exception:
                logger.error("MCP tool invocation logger failed")


def create_default_connector_tool_invocation_logger(
    sink: McpToolInvocationLogSink,
    audit_recorder: McpAuditRecorder,
) -> ConnectorToolInvocationLogger:
    return CompositeConnectorToolInvocationLogger(
        InvocationLogSinkToolInvocationLogger(sink),
        AuditToolInvocationLogger(audit_recorder),
    )


_AUDIT_FAILURE_CATEGORIES: dict[McpToolInvocationFailureCategory, McpAuditFailureCategory] = {
    McpToolInvocationFailureCategory.VALIDATION: McpAuditFailureCategory.VALIDATION,
    McpToolInvocationFailureCategory.AUTHORIZATION: McpAuditFailureCategory.AUTHORIZATION,
    McpToolInvocationFailureCategory.CONNECTOR_ERROR: McpAuditFailureCategory.CONNECTOR_ERROR,
    McpToolInvocationFailureCategory.UNEXPECTED_ERROR: McpAuditFailureCategory.UNEXPECTED_ERROR,
}


def _audit_result(event: McpToolInvocationCompleted) -> McpAuditSuccess | McpAuditFailure:
    if isinstance(event, McpToolInvocationFailed):
        return McpAuditFailure(_AUDIT_FAILURE_CATEGORIES[event.failure_category])
    return McpAuditSuccess()
