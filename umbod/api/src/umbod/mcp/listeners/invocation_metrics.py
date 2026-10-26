from umbod.mcp.metrics import (
    CompletedToolInvocation,
    InvocationOutcome,
    InvocationScope,
    McpMetricsRecorder,
    ToolInvocationMetricIdentity,
)
from umbod.mcp.signals.channels import McpSignals
from umbod.mcp.signals.events import McpToolIdentity, McpToolInvocationCompleted, ToolInventoryObserved


def metric_identity(identity: McpToolIdentity) -> ToolInvocationMetricIdentity:
    return ToolInvocationMetricIdentity(
        scope=InvocationScope.CONNECTOR if identity.connector_id is not None else InvocationScope.REQUEST,
        connector_name=identity.connector_id or "internal",
        tool_name=identity.tool_name,
    )


class InvocationMetricsReceiver:
    def __init__(self, recorder: McpMetricsRecorder) -> None:
        self._recorder = recorder

    def __call__(self, event: McpToolInvocationCompleted) -> None:
        self._recorder.record_completed_invocation(
            CompletedToolInvocation(
                **metric_identity(event.started.tool).model_dump(),
                outcome=InvocationOutcome(event.outcome.value),
                duration_seconds=max(event.duration_ms / 1000, 1e-12),
            )
        )


class InventoryMetricsReceiver:
    def __init__(self, recorder: McpMetricsRecorder, signals: McpSignals) -> None:
        self._recorder = recorder
        self._signals = signals

    def __call__(self, event: ToolInventoryObserved) -> None:
        for identity in event.identities:
            try:
                self._recorder.initialize_invocation(metric_identity(identity))
            except Exception as error:
                self._signals.report_failure("mcp.inventory.metrics", error)
