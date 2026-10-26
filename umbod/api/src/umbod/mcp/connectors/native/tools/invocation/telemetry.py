import asyncio
from collections.abc import Callable

from umbod.core.invocation.failure_evidence import (
    InvocationFailureOrigin,
    InvocationReturnedFailure,
    current_invocation_failure,
    exception_evidence,
)
from umbod.core.invocation.tools.execution import ToolExecutionContext, ToolExecutionFailed, ToolExecutionOutcome, ToolExecutionRequest, ToolExecutionSucceeded
from umbod.mcp.connectors.native.approval import ModernConnectorApprovalRequired
from umbod.mcp.connectors.native.tools.invocation.lifecycle import ConnectorInvocationLifecycle, ConnectorToolInvocationIdentity
from umbod.mcp.logging import ConnectorToolInvocationLogger, McpToolInvocationFailureCategory
from umbod.mcp.metrics import McpMetricsRecorder
from umbod.mcp.tools.invocation.diagnostics import invocation_failure
from umbod.mcp.tools.invocation.telemetry import McpToolInvocationObserver, log_observation_failure


class ConnectorTelemetryInterceptor:
    def __init__(
        self,
        connector_name: str,
        tool_invocation_logger: ConnectorToolInvocationLogger,
        metrics_recorder: McpMetricsRecorder,
        result_is_error: Callable[[object], bool],
    ) -> None:
        self._connector_name = connector_name
        self._observer = McpToolInvocationObserver(tool_invocation_logger, metrics_recorder)
        self._result_is_error = result_is_error

    async def before_tool_preparation(self, request: ToolExecutionRequest) -> object:
        identity = request.identity
        connector_identity = ConnectorToolInvocationIdentity(
            tool_name=request.public_tool_name,
            connector_id=identity.connector_id,
            connector_name=self._connector_name,
            operation_name=identity.capability_key,
        )
        return self._observer.start(connector_identity.normalized())

    async def before_tool_execution(self, context: ToolExecutionContext, state: object) -> None:
        return None

    async def after_tool_execution(self, request: ToolExecutionRequest, outcome: ToolExecutionOutcome, state: object) -> None:
        if isinstance(outcome, ToolExecutionFailed) and isinstance(outcome.error, (ModernConnectorApprovalRequired, asyncio.CancelledError)):
            return
        if state is not None and not isinstance(state, ConnectorInvocationLifecycle):
            raise TypeError("Invalid connector invocation lifecycle state")
        if isinstance(outcome, ToolExecutionFailed):
            evidence = current_invocation_failure() or exception_evidence(outcome.error, InvocationFailureOrigin.INTERNAL)
            self._observer.failed(state, McpToolInvocationFailureCategory.CONNECTOR_ERROR, invocation_failure.get(), evidence)
            return
        try:
            returned_error = isinstance(outcome, ToolExecutionSucceeded) and self._result_is_error(outcome.result)
        except Exception as error:
            log_observation_failure("Connector tool result classification failed", error)
            self._observer.failed(state, McpToolInvocationFailureCategory.CONNECTOR_ERROR, invocation_failure.get(), exception_evidence(error, InvocationFailureOrigin.INTERNAL))
            return
        if returned_error:
            evidence = current_invocation_failure()
            if evidence is None:
                returned_origin = {
                    "native": InvocationFailureOrigin.CONNECTOR,
                    "downstream_mcp": InvocationFailureOrigin.MCP,
                    "openapi": InvocationFailureOrigin.OPENAPI,
                }.get(request.identity.connector_kind, InvocationFailureOrigin.INTERNAL)
                evidence = InvocationReturnedFailure(returned_origin)
            self._observer.failed(state, McpToolInvocationFailureCategory.CONNECTOR_ERROR, invocation_failure.get(), evidence)
        else:
            self._observer.succeeded(state)
