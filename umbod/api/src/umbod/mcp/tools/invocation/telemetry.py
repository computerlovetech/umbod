import logging
from dataclasses import replace

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic
from umbod.core.invocation.failure_evidence import (
    InvocationFailureEvidence,
)

from umbod.logging import log_safe_exception
from umbod.mcp.logging import (
    ConnectorToolInvocationLogger,
    McpToolIdentity,
    McpToolInvocationCompleted,
    McpToolInvocationFailureCategory,
)
from umbod.mcp.metrics import CompletedToolInvocation, InvocationOutcome, McpMetricsRecorder
from umbod.mcp.tools.invocation.lifecycle import McpToolInvocationLifecycle

logger = logging.getLogger(__name__)


def log_observation_failure(message: str, error: BaseException) -> None:
    log_safe_exception(logger, message, error)


class McpToolInvocationObserver:
    def __init__(self, tool_invocation_logger: ConnectorToolInvocationLogger, metrics_recorder: McpMetricsRecorder) -> None:
        self._tool_invocation_logger = tool_invocation_logger
        self._metrics_recorder = metrics_recorder

    def start(self, identity: McpToolIdentity) -> McpToolInvocationLifecycle | None:
        try:
            return McpToolInvocationLifecycle.start(identity)
        except Exception as error:
            log_observation_failure("MCP tool invocation lifecycle start failed", error)
            return None

    def succeeded(self, lifecycle: McpToolInvocationLifecycle | None) -> None:
        if lifecycle is None:
            return
        try:
            completed = lifecycle.succeeded()
        except Exception as error:
            log_observation_failure("MCP tool invocation success completion failed", error)
            return
        self._record(completed, InvocationOutcome.SUCCESS)

    def failed(self, lifecycle: McpToolInvocationLifecycle | None, category: McpToolInvocationFailureCategory, diagnostic: InvocationFailureDiagnostic | None, evidence: InvocationFailureEvidence) -> None:
        if lifecycle is None:
            return
        try:
            completed = replace(lifecycle.failed(category), diagnostic=diagnostic, evidence=evidence)
        except Exception as error:
            log_observation_failure("MCP tool invocation failure completion failed", error)
            return
        self._record(completed, InvocationOutcome.FAILURE)

    def _record(self, completed: McpToolInvocationCompleted, outcome: InvocationOutcome) -> None:
        try:
            self._tool_invocation_logger.record_tool_invocation_completed(completed)
        except Exception as error:
            log_observation_failure("MCP tool invocation logging failed", error)
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
        except Exception as error:
            log_observation_failure("MCP tool metrics recording failed", error)
