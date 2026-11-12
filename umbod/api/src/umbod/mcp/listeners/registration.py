from umbod.core.diagnostics import ApplicationFailure, PublishingSignalFailureHandler
from umbod.core.signals import SignalPublisher
from umbod.logging import emit_structured_record
from umbod.mcp.listeners.capability_logging import CapabilityLoggingReceiver
from umbod.mcp.listeners.invocation_audit import InvocationAuditReceiver
from umbod.mcp.listeners.invocation_logging import InvocationLoggingReceiver
from umbod.mcp.listeners.invocation_metrics import InventoryMetricsReceiver, InvocationMetricsReceiver
from umbod.mcp.logging.audit.recorder import McpAuditRecorder
from umbod.mcp.logging.invocation.sink import McpToolInvocationLogSink
from umbod.mcp.metrics import McpMetricsRecorder
from umbod.mcp.signals.channels import McpSignals


def register_mcp_listeners(
    signals: McpSignals,
    log_sink: McpToolInvocationLogSink,
    metrics_recorder: McpMetricsRecorder,
    audit_recorder: McpAuditRecorder,
) -> None:
    names = (
        (signals.capability_completed, "mcp.capability.logging"),
        (signals.invocation_completed, "mcp.invocation.logging"),
        (signals.invocation_completed, "mcp.invocation.metrics"),
        (signals.invocation_completed, "mcp.invocation.audit"),
        (signals.tool_inventory_observed, "mcp.inventory.metrics"),
    )
    for signal, name in names:
        if signal.is_connected(name):
            raise ValueError(f"Signal receiver name already registered: {name}")
    signals.capability_completed.connect("mcp.capability.logging", CapabilityLoggingReceiver(emit_structured_record))
    signals.invocation_completed.connect("mcp.invocation.logging", InvocationLoggingReceiver(log_sink))
    signals.invocation_completed.connect("mcp.invocation.metrics", InvocationMetricsReceiver(metrics_recorder))
    signals.invocation_completed.connect("mcp.invocation.audit", InvocationAuditReceiver(audit_recorder))
    signals.tool_inventory_observed.connect("mcp.inventory.metrics", InventoryMetricsReceiver(metrics_recorder, signals))


def create_mcp_signals(
    log_sink: McpToolInvocationLogSink,
    metrics_recorder: McpMetricsRecorder,
    audit_recorder: McpAuditRecorder,
    application_failures: SignalPublisher[ApplicationFailure],
) -> McpSignals:
    signals = McpSignals(PublishingSignalFailureHandler(application_failures))
    register_mcp_listeners(signals, log_sink, metrics_recorder, audit_recorder)
    return signals
