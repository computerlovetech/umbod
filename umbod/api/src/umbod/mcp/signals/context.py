from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field

from umbod.mcp.signals.events import McpInvocationActor, McpInvocationCorrelation, McpToolInvocationFailureCategory


_FAILURE_PRIORITY = {
    McpToolInvocationFailureCategory.TOOL_ERROR: 0,
    McpToolInvocationFailureCategory.AUTHORIZATION: 1,
    McpToolInvocationFailureCategory.VALIDATION: 2,
    McpToolInvocationFailureCategory.CONNECTOR_ERROR: 3,
    McpToolInvocationFailureCategory.UNEXPECTED_ERROR: 4,
}


class McpInvocationFailureTracker:
    def __init__(self) -> None:
        self._categories: set[McpToolInvocationFailureCategory] = set()

    def record(self, category: McpToolInvocationFailureCategory) -> None:
        self._categories.add(category)

    @property
    def category(self) -> McpToolInvocationFailureCategory:
        return max(self._categories, key=_FAILURE_PRIORITY.__getitem__, default=McpToolInvocationFailureCategory.TOOL_ERROR)


@dataclass(frozen=True)
class McpInvocationContext:
    actor: McpInvocationActor
    correlation: McpInvocationCorrelation
    server_name: str
    failures: McpInvocationFailureTracker = field(default_factory=McpInvocationFailureTracker)


_mcp_invocation_context: ContextVar[McpInvocationContext | None] = ContextVar(
    "mcp_invocation_context", default=None
)


def set_mcp_invocation_context(context: McpInvocationContext) -> Token[McpInvocationContext | None]:
    return _mcp_invocation_context.set(context)


def reset_mcp_invocation_context(token: Token[McpInvocationContext | None]) -> None:
    _mcp_invocation_context.reset(token)


def current_mcp_invocation_context() -> McpInvocationContext | None:
    return _mcp_invocation_context.get()
