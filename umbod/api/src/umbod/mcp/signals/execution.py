import asyncio

from umbod.core.usage.models import ConnectorUsageToolTarget
from collections.abc import Callable
from typing import Any, Protocol

from fastmcp.exceptions import AuthorizationError, ValidationError

from umbod.core.invocation.diagnostics import NoInvocationFailureDiagnostic
from umbod.core.invocation.failure_assessment import (
    InvocationFailureAssessment,
    InvocationFailureCategory,
    InvocationRejectionKind,
    NoInvocationFailureEvidence,
    assess_raised_invocation_failure,
    assess_returned_invocation_failure,
)
from umbod.core.invocation.policy import ConnectorInvocationDenied, ConnectorInvocationPolicy

from umbod.core.invocation.failure_evidence import (
    InvocationFailureOrigin,
    current_invocation_failure,
    exception_evidence,
)
from umbod.core.invocation.tools.execution import ToolExecutionContext, ToolExecutionFailed, ToolExecutionOutcome, ToolExecutionRequest, ToolExecutionSucceeded
from umbod.mcp.connectors.native.approval import ModernConnectorApprovalRequired
from umbod.mcp.signals.channels import McpSignals
from umbod.mcp.signals.events import McpToolIdentity, McpToolInvocationFailureCategory
from umbod.mcp.signals.lifecycle import McpToolInvocationLifecycle, UnavailableToolInvocationLifecycle
from umbod.mcp.signals.diagnostics import invocation_failure
from umbod.mcp.signals.ports import McpInvocationPublishing
from umbod.mcp.signals.publisher import McpInvocationPublisher
from umbod.mcp.tools.errors import ToolAuthorizationDenied
from umbod.core.invocation.tools.execution import ToolExecutionPipeline, create_tool_execution_pipeline


class ConnectorInvocationSignalInterceptor:
    def __init__(
        self,
        connector_name: str,
        publisher: McpInvocationPublishing,
        result_is_error: Callable[[object], bool],
    ) -> None:
        self._connector_name = connector_name
        self._publisher = publisher
        self._result_is_error = result_is_error

    async def before_tool_preparation(self, request: ToolExecutionRequest) -> McpToolInvocationLifecycle | UnavailableToolInvocationLifecycle:
        identity = request.identity
        connector_identity = McpToolIdentity(
            tool_name=request.public_tool_name,
            connector_id=identity.connector_id.strip()[:256] or "unknown",
            connector_name=self._connector_name.strip()[:256] or identity.connector_id.strip()[:256] or "unknown",
            operation_name=identity.capability_key,
            usage_target=ConnectorUsageToolTarget(
                kind='connector', connector_kind=identity.connector_kind,
                connector_id=identity.connector_id, capability_key=identity.capability_key,
            ),
        )
        return self._publisher.start(connector_identity)

    async def before_tool_execution(self, context: ToolExecutionContext, state: object) -> None:
        return None

    async def after_tool_execution(self, request: ToolExecutionRequest, outcome: ToolExecutionOutcome, state: object) -> None:
        if not isinstance(state, (McpToolInvocationLifecycle, UnavailableToolInvocationLifecycle)):
            raise TypeError("Invalid connector invocation lifecycle state")
        if isinstance(state, UnavailableToolInvocationLifecycle):
            return
        if isinstance(outcome, ToolExecutionFailed) and isinstance(outcome.error, (ModernConnectorApprovalRequired, asyncio.CancelledError)):
            return
        context_diagnostic = invocation_failure.get()
        diagnostic = context_diagnostic if context_diagnostic is not None else NoInvocationFailureDiagnostic()
        if isinstance(outcome, ToolExecutionFailed):
            evidence = current_invocation_failure()
            assessment = assess_raised_invocation_failure(
                outcome.error,
                rejection=_exception_rejection(outcome.error),
                diagnostic=diagnostic,
                evidence=evidence if evidence is not None else NoInvocationFailureEvidence(),
            )
            self._publish_failure(state, assessment)
            return
        try:
            returned_error = isinstance(outcome, ToolExecutionSucceeded) and self._result_is_error(outcome.result)
        except Exception as error:
            self._publisher.report_failure("Connector tool result classification failed", error)
            self._publisher.failed(state, McpToolInvocationFailureCategory.CONNECTOR_ERROR, diagnostic, exception_evidence(error, InvocationFailureOrigin.INTERNAL))
            return
        if returned_error:
            evidence = current_invocation_failure()
            assessment = assess_returned_invocation_failure(
                request.identity.connector_kind,
                diagnostic=diagnostic,
                evidence=evidence if evidence is not None else NoInvocationFailureEvidence(),
            )
            self._publish_failure(state, assessment)
        else:
            self._publisher.succeeded(state)

    def _publish_failure(self, state: McpToolInvocationLifecycle, assessment: InvocationFailureAssessment) -> None:
        category = {
            InvocationFailureCategory.VALIDATION: McpToolInvocationFailureCategory.VALIDATION,
            InvocationFailureCategory.AUTHORIZATION: McpToolInvocationFailureCategory.AUTHORIZATION,
            InvocationFailureCategory.TOOL_ERROR: McpToolInvocationFailureCategory.TOOL_ERROR,
            InvocationFailureCategory.CONNECTOR_ERROR: McpToolInvocationFailureCategory.CONNECTOR_ERROR,
        }[assessment.category]
        self._publisher.failed(state, category, assessment.diagnostic, assessment.evidence)


def _exception_rejection(error: BaseException) -> InvocationRejectionKind:
    if isinstance(error, ValidationError):
        return InvocationRejectionKind.VALIDATION
    if isinstance(error, (ConnectorInvocationDenied, AuthorizationError, ToolAuthorizationDenied)):
        return InvocationRejectionKind.AUTHORIZATION
    return InvocationRejectionKind.NONE


class McpToolExecutionPipelineFactory(Protocol):
    def create(self, connector_name: str, result_is_error: Callable[[object], bool]) -> ToolExecutionPipeline[Any]: ...


class SignalToolExecutionPipelineFactory:
    def __init__(self, signals: McpSignals, invocation_policy: ConnectorInvocationPolicy) -> None:
        self._signals = signals
        self._invocation_policy = invocation_policy

    def create(self, connector_name: str, result_is_error: Callable[[object], bool]) -> ToolExecutionPipeline[Any]:
        return create_tool_execution_pipeline(
            self._invocation_policy,
            (ConnectorInvocationSignalInterceptor(connector_name, McpInvocationPublisher(self._signals), result_is_error),),
        )
