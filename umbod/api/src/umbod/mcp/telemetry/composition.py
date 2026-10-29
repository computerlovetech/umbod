from dataclasses import dataclass

from umbod.mcp.logging import create_default_mcp_audit_recorder, create_default_mcp_tool_invocation_log_sink
from umbod.mcp.metrics import PrometheusMcpMetricsRecorder
from umbod.mcp.metrics.http_server import McpMetricsHttpServer
from umbod.mcp.settings import MCPAppSettings
from umbod.mcp.telemetry.dependencies import McpTelemetryDependencies
from umbod.mcp.telemetry.ports import McpMetricsServerFactory


@dataclass(frozen=True)
class ConfiguredMcpMetricsServerFactory(McpMetricsServerFactory):
    recorder: PrometheusMcpMetricsRecorder
    port: int
    host: str

    def create(self) -> McpMetricsHttpServer:
        return McpMetricsHttpServer(self.recorder, self.port, self.host)


def create_configured_mcp_telemetry(settings: MCPAppSettings) -> McpTelemetryDependencies:
    recorder = PrometheusMcpMetricsRecorder()
    return McpTelemetryDependencies(
        invocation_log_sink=create_default_mcp_tool_invocation_log_sink(),
        audit_recorder=create_default_mcp_audit_recorder(settings.runtime.app_name),
        metrics_recorder=recorder,
        metrics_server_factory=ConfiguredMcpMetricsServerFactory(recorder, settings.mcp.metrics_port, "0.0.0.0"),
    )
