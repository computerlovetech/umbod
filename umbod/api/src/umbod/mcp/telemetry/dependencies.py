from dataclasses import dataclass

from umbod.mcp.logging import McpAuditRecorder, McpToolInvocationLogSink
from umbod.mcp.telemetry.ports import McpApplicationMetricsRecorder, McpMetricsServerFactory


@dataclass(frozen=True)
class McpTelemetryDependencies:
    invocation_log_sink: McpToolInvocationLogSink
    audit_recorder: McpAuditRecorder
    metrics_recorder: McpApplicationMetricsRecorder
    metrics_server_factory: McpMetricsServerFactory
