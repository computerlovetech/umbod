from dataclasses import dataclass

from fastmcp.exceptions import AuthorizationError, ValidationError
from fastmcp.tools import InputRequiredToolResult, ToolResult
from mcp.shared.exceptions import MCPError

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic, NoInvocationFailureDiagnostic
from umbod.core.invocation.failure_evidence import (
    InvocationFailureEvidence,
    InvocationFailureOrigin,
    InvocationRejectedFailure,
    exception_evidence,
)
from umbod.core.invocation.tools.ordered_execution import ToolExecutionFailed, ToolExecutionOutcome
from umbod.mcp.signals.events import McpToolIdentity, McpToolInvocationFailureCategory
from umbod.mcp.signals.lifecycle import McpToolInvocationLifecycle, UnavailableToolInvocationLifecycle
from umbod.mcp.signals.publisher import IsolatedInvocationPublishing
from umbod.mcp.tools.errors import BuiltinToolRejected, ToolAuthorizationDenied, ToolResponseContractError


@dataclass(frozen=True)
class ObservedToolFailure:
    category: McpToolInvocationFailureCategory
    evidence: InvocationFailureEvidence
    diagnostic: InvocationFailureDiagnostic | NoInvocationFailureDiagnostic

    @classmethod
    def unexpected(cls, error: Exception) -> "ObservedToolFailure":
        return cls(
            McpToolInvocationFailureCategory.UNEXPECTED_ERROR,
            exception_evidence(error, InvocationFailureOrigin.INTERNAL),
            NoInvocationFailureDiagnostic(),
        )


@dataclass(frozen=True)
class ObservedToolResponse:
    result: ToolResult
    failure: ObservedToolFailure | None


class ObservedToolSignalInterceptor:
    def __init__(self, publisher: IsolatedInvocationPublishing) -> None:
        self._publisher = publisher

    async def before_tool_preparation(
        self, request: McpToolIdentity,
    ) -> McpToolInvocationLifecycle | UnavailableToolInvocationLifecycle:
        return self._publisher.start(request)

    async def before_tool_execution(self, context: None, state: object) -> None:
        return None

    async def after_tool_execution(self, request: McpToolIdentity, outcome: ToolExecutionOutcome, state: object) -> None:
        if not isinstance(state, (McpToolInvocationLifecycle, UnavailableToolInvocationLifecycle)):
            return
        if isinstance(outcome, ToolExecutionFailed):
            failure = classify_raised_failure(outcome.error)
        else:
            response = outcome.result
            if not isinstance(response, ObservedToolResponse) or isinstance(response.result, InputRequiredToolResult):
                return
            failure = response.failure
            if failure is None:
                self._publisher.succeeded(state)
        if failure is not None:
            self._publisher.failed(state, failure.category, failure.diagnostic, failure.evidence)


def classify_raised_failure(error: BaseException) -> ObservedToolFailure | None:
    if not isinstance(error, Exception) or isinstance(error, (AuthorizationError, MCPError)):
        return None
    if isinstance(error, ToolResponseContractError):
        return ObservedToolFailure(
            McpToolInvocationFailureCategory.UNEXPECTED_ERROR,
            exception_evidence(error, InvocationFailureOrigin.INTERNAL),
            InvocationFailureDiagnostic(execution_mode="shared", stage="output", reason="invalid_output"),
        )
    if isinstance(error, ToolAuthorizationDenied):
        category = McpToolInvocationFailureCategory.AUTHORIZATION
    elif isinstance(error, ValidationError):
        category = McpToolInvocationFailureCategory.VALIDATION
    elif isinstance(error, BuiltinToolRejected):
        category = McpToolInvocationFailureCategory.TOOL_ERROR
    else:
        return ObservedToolFailure.unexpected(error)
    return ObservedToolFailure(
        category,
        InvocationRejectedFailure(InvocationFailureOrigin.CLIENT_INPUT),
        NoInvocationFailureDiagnostic(),
    )
