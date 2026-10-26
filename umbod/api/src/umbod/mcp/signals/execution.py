import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from umbod.core.invocation.policy import ConnectorInvocationPolicy

from umbod.core.invocation.failure_evidence import (
    InvocationFailureOrigin,
    InvocationReturnedFailure,
    current_invocation_failure,
    exception_evidence,
)
from umbod.core.invocation.tools.execution import ToolExecutionContext, ToolExecutionFailed, ToolExecutionOutcome, ToolExecutionRequest, ToolExecutionSucceeded
from umbod.mcp.connectors.native.approval import ModernConnectorApprovalRequired
from umbod.mcp.signals.channels import McpSignals
from umbod.mcp.signals.events import McpToolIdentity, McpToolInvocationFailureCategory
from umbod.mcp.signals.lifecycle import McpToolInvocationLifecycle
from umbod.mcp.signals.diagnostics import invocation_failure
from umbod.mcp.signals.publisher import McpInvocationPublisher
from umbod.core.invocation.tools.execution import ToolExecutionPipeline, create_tool_execution_pipeline


class ConnectorInvocationSignalInterceptor:
    def __init__(
        self,
        connector_name: str,
        signals: McpSignals,
        result_is_error: Callable[[object], bool],
    ) -> None:
        self._connector_name = connector_name
        self._signals = signals
        self._publisher = McpInvocationPublisher(signals)
        self._result_is_error = result_is_error

    async def before_tool_preparation(self, request: ToolExecutionRequest) -> object:
        identity = request.identity
        connector_identity = McpToolIdentity(
            tool_name=request.public_tool_name,
            connector_id=identity.connector_id.strip()[:256] or "unknown",
            connector_name=self._connector_name.strip()[:256] or identity.connector_id.strip()[:256] or "unknown",
            operation_name=identity.capability_key,
        )
        return self._publisher.start(connector_identity)

    async def before_tool_execution(self, context: ToolExecutionContext, state: object) -> None:
        return None

    async def after_tool_execution(self, request: ToolExecutionRequest, outcome: ToolExecutionOutcome, state: object) -> None:
        if isinstance(outcome, ToolExecutionFailed) and isinstance(outcome.error, (ModernConnectorApprovalRequired, asyncio.CancelledError)):
            return
        if state is not None and not isinstance(state, McpToolInvocationLifecycle):
            raise TypeError("Invalid connector invocation lifecycle state")
        if isinstance(outcome, ToolExecutionFailed):
            evidence = current_invocation_failure() or exception_evidence(outcome.error, InvocationFailureOrigin.INTERNAL)
            self._publisher.failed(state, McpToolInvocationFailureCategory.CONNECTOR_ERROR, invocation_failure.get(), evidence)
            return
        try:
            returned_error = isinstance(outcome, ToolExecutionSucceeded) and self._result_is_error(outcome.result)
        except Exception as error:
            self._signals.report_failure("Connector tool result classification failed", error)
            self._publisher.failed(state, McpToolInvocationFailureCategory.CONNECTOR_ERROR, invocation_failure.get(), exception_evidence(error, InvocationFailureOrigin.INTERNAL))
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
            self._publisher.failed(state, McpToolInvocationFailureCategory.CONNECTOR_ERROR, invocation_failure.get(), evidence)
        else:
            self._publisher.succeeded(state)


class McpToolExecutionPipelineFactory(Protocol):
    def create(self, connector_name: str, result_is_error: Callable[[object], bool]) -> ToolExecutionPipeline[Any]: ...


class SignalToolExecutionPipelineFactory:
    def __init__(self, signals: McpSignals, invocation_policy: ConnectorInvocationPolicy) -> None:
        self._signals = signals
        self._invocation_policy = invocation_policy

    def create(self, connector_name: str, result_is_error: Callable[[object], bool]) -> ToolExecutionPipeline[Any]:
        return create_tool_execution_pipeline(
            self._invocation_policy,
            (ConnectorInvocationSignalInterceptor(connector_name, self._signals, result_is_error),),
        )
