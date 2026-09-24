from typing import Protocol

from umbod.mcp.metrics.models import CompletedToolInvocation


class McpMetricsRecorder(Protocol):
    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None: ...
