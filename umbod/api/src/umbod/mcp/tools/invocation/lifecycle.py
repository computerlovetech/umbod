import time
import uuid

from umbod.mcp.logging import (
    McpInteractionType,
    McpInvocationActor,
    McpInvocationCorrelation,
    McpToolIdentity,
    McpToolInvocationFailed,
    McpToolInvocationFailureCategory,
    McpToolInvocationStarted,
    McpToolInvocationSucceeded,
    current_mcp_invocation_context,
)


class McpToolInvocationLifecycle:
    def __init__(self, started: McpToolInvocationStarted, started_monotonic: float) -> None:
        self._started = started
        self._started_monotonic = started_monotonic

    @classmethod
    def start(cls, identity: McpToolIdentity) -> "McpToolInvocationLifecycle":
        context = current_mcp_invocation_context()
        actor = context.actor if context is not None else McpInvocationActor()
        correlation = context.correlation if context is not None else McpInvocationCorrelation(trace_id=uuid.uuid4().hex)
        return cls(
            McpToolInvocationStarted(
                interaction_type=McpInteractionType.TOOL_INVOCATION,
                tool=identity,
                actor=actor,
                started_at_unix_nano=time.time_ns(),
                correlation=correlation,
            ),
            time.monotonic(),
        )

    def succeeded(self) -> McpToolInvocationSucceeded:
        return McpToolInvocationSucceeded(started=self._started, duration_ms=self._duration_ms())

    def failed(self, failure_category: McpToolInvocationFailureCategory) -> McpToolInvocationFailed:
        return McpToolInvocationFailed(started=self._started, duration_ms=self._duration_ms(), failure_category=failure_category)

    def _duration_ms(self) -> float:
        return (time.monotonic() - self._started_monotonic) * 1000
