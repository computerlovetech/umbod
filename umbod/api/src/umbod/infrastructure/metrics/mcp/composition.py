from dataclasses import dataclass

from umbod.infrastructure.metrics.mcp.http_server import McpMetricsHttpServer
from umbod.infrastructure.metrics.mcp.prometheus import PrometheusMcpMetricsRecorder
from umbod.mcp.telemetry.dependencies import McpMetricsDependencies
from umbod.mcp.telemetry.ports import McpMetricsServerFactory


@dataclass(frozen=True)
class ConfiguredMcpMetricsServerFactory(McpMetricsServerFactory):
    recorder: PrometheusMcpMetricsRecorder
    port: int
    host: str

    def create(self) -> McpMetricsHttpServer:
        return McpMetricsHttpServer(self.recorder, self.port, self.host)


def create_mcp_metrics(port: int, host: str) -> McpMetricsDependencies:
    recorder = PrometheusMcpMetricsRecorder()
    return McpMetricsDependencies(
        recorder=recorder,
        server_factory=ConfiguredMcpMetricsServerFactory(recorder, port, host),
    )
