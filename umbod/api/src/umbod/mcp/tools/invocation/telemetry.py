import logging

from umbod.mcp.logging import (
    ConnectorToolInvocationLogger,
    McpToolIdentity,
    McpToolInvocationCompleted,
    McpToolInvocationFailureCategory,
)
from umbod.mcp.metrics import CompletedToolInvocation, InvocationOutcome, McpMetricsRecorder
from umbod.mcp.tools.invocation.lifecycle import McpToolInvocationLifecycle

logger = logging.getLogger(__name__)


class McpToolInvocationObserver:
    def __init__(self, tool_invocation_logger: ConnectorToolInvocationLogger, metrics_recorder: McpMetricsRecorder) -> None:
        self._tool_invocation_logger = tool_invocation_logger
        self._metrics_recorder = metrics_recorder

    def start(self, identity: McpToolIdentity) -> McpToolInvocationLifecycle | None:
        try:
            return McpToolInvocationLifecycle.start(identity)
        except Exception:
            logger.error("MCP tool invocation lifecycle start failed")
            return None

    def succeeded(self, lifecycle: McpToolInvocationLifecycle | None) -> None:
        if lifecycle is None:
            return
        try:
            completed = lifecycle.succeeded()
        except Exception:
            logger.error("MCP tool invocation success completion failed")
            return
        self._record(completed, InvocationOutcome.SUCCESS)

    def failed(self, lifecycle: McpToolInvocationLifecycle | None, category: McpToolInvocationFailureCategory) -> None:
        if lifecycle is None:
            return
        try:
            completed = lifecycle.failed(category)
        except Exception:
            logger.error("MCP tool invocation failure completion failed")
            return
        self._record(completed, InvocationOutcome.FAILURE)

    def _record(self, completed: McpToolInvocationCompleted, outcome: InvocationOutcome) -> None:
        try:
            self._tool_invocation_logger.record_tool_invocation_completed(completed)
        except Exception:
            logger.error("MCP tool invocation logging failed")
        identity = completed.started.tool
        try:
            self._metrics_recorder.record_completed_invocation(
                CompletedToolInvocation(
                    connector_name=identity.connector_id or "internal",
                    tool_name=identity.tool_name,
                    outcome=outcome,
                    duration_seconds=completed.duration_ms / 1000,
                )
            )
        except Exception:
            logger.error("MCP tool metrics recording failed")
