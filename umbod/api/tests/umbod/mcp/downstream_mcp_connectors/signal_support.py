from typing import Callable

from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.logging import McpAuditEvent, McpAuditRecorder
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import InMemoryMcpToolInvocationLogSink
from umbod.mcp.metrics import McpMetricsRecorder
from umbod.mcp.signals import McpSignals, McpToolInvocationCompleted


class DiscardingAuditSink:
    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        return None


def invocation_signals(metrics: McpMetricsRecorder, *completion_receivers: Callable[[McpToolInvocationCompleted], None]) -> McpSignals:
    signals = create_mcp_signals(
        InMemoryMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter()),
        metrics,
        McpAuditRecorder(DiscardingAuditSink(), "test"),
    )
    for index, receiver in enumerate(completion_receivers):
        signals.invocation_completed.connect(f"test.invocation.{index}", receiver)
    return signals
