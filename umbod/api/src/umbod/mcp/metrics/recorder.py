from typing import Protocol

from umbod.mcp.metrics.models import CompletedToolInvocation, ToolInvocationMetricIdentity


class McpMetricsRecorder(Protocol):
    def initialize_invocation(self, identity: ToolInvocationMetricIdentity) -> None: ...

    def record_completed_invocation(self, invocation: CompletedToolInvocation) -> None: ...
