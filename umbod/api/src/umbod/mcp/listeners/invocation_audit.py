import uuid

from umbod.mcp.logging.audit.event import (
    McpAuditCorrelation,
    McpAuditFailure,
    McpAuditFailureCategory,
    McpAuditSuccess,
)
from umbod.mcp.logging.audit.identity import audit_identity_from_invocation_actor
from umbod.mcp.logging.audit.recorder import McpAuditRecorder
from umbod.mcp.signals import (
    McpInvocationCorrelation,
    McpToolInvocationCompleted,
    McpToolInvocationFailed,
    McpToolInvocationFailureCategory,
)


_AUDIT_FAILURE_CATEGORIES: dict[McpToolInvocationFailureCategory, McpAuditFailureCategory] = {
    McpToolInvocationFailureCategory.VALIDATION: McpAuditFailureCategory.VALIDATION,
    McpToolInvocationFailureCategory.AUTHORIZATION: McpAuditFailureCategory.AUTHORIZATION,
    McpToolInvocationFailureCategory.CONNECTOR_ERROR: McpAuditFailureCategory.CONNECTOR_ERROR,
    McpToolInvocationFailureCategory.UNEXPECTED_ERROR: McpAuditFailureCategory.UNEXPECTED_ERROR,
}


class InvocationAuditReceiver:
    def __init__(self, recorder: McpAuditRecorder) -> None:
        self._recorder = recorder

    def __call__(self, event: McpToolInvocationCompleted) -> None:
        started = event.started
        identity = started.tool
        if identity.connector_id is None and identity.tool_name in {"search_tools", "execute_tool", "execute_code"}:
            return
        correlation = started.correlation or McpInvocationCorrelation(trace_id=uuid.uuid4().hex)
        result = (
            McpAuditFailure(_AUDIT_FAILURE_CATEGORIES[event.failure_category])
            if isinstance(event, McpToolInvocationFailed)
            else McpAuditSuccess()
        )
        self._recorder.record_tool_invocation(
            identity=audit_identity_from_invocation_actor(started.actor),
            target=self._recorder.tool_target(identity),
            result=result,
            correlation=McpAuditCorrelation(trace_id=correlation.trace_id, span_id=correlation.span_id),
            occurred_at_unix_nano=started.started_at_unix_nano,
        )
