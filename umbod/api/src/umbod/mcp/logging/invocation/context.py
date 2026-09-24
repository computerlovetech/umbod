from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from umbod.mcp.logging.invocation.event import McpInvocationActor, McpInvocationCorrelation


@dataclass(frozen=True)
class McpInvocationContext:
    actor: McpInvocationActor
    correlation: McpInvocationCorrelation
    server_name: str


_mcp_invocation_context: ContextVar[McpInvocationContext | None] = ContextVar(
    "mcp_invocation_context", default=None
)


def set_mcp_invocation_context(context: McpInvocationContext) -> None:
    _mcp_invocation_context.set(context)


def current_mcp_invocation_context() -> McpInvocationContext | None:
    return _mcp_invocation_context.get()
