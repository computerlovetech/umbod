from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

from umbod.mcp.signals.events import McpInvocationActor, McpInvocationCorrelation


@dataclass(frozen=True)
class McpInvocationContext:
    actor: McpInvocationActor
    correlation: McpInvocationCorrelation
    server_name: str


_mcp_invocation_context: ContextVar[McpInvocationContext | None] = ContextVar(
    "mcp_invocation_context", default=None
)


def set_mcp_invocation_context(context: McpInvocationContext) -> Token[McpInvocationContext | None]:
    return _mcp_invocation_context.set(context)


def reset_mcp_invocation_context(token: Token[McpInvocationContext | None]) -> None:
    _mcp_invocation_context.reset(token)


def current_mcp_invocation_context() -> McpInvocationContext | None:
    return _mcp_invocation_context.get()
