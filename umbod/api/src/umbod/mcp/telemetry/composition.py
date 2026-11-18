from umbod.infrastructure.metrics.mcp import create_mcp_metrics

from umbod.logging import create_application_failure_signal

from umbod.mcp.logging import create_default_mcp_audit_recorder, create_default_mcp_tool_invocation_log_sink
from umbod.mcp.settings import MCPAppSettings
from umbod.mcp.telemetry.dependencies import McpTelemetryDependencies


def create_configured_mcp_telemetry(settings: MCPAppSettings) -> McpTelemetryDependencies:
    application_failures = create_application_failure_signal()
    metrics = create_mcp_metrics(settings.mcp.metrics_port, "0.0.0.0")
    return McpTelemetryDependencies(
        application_failures=application_failures,
        invocation_log_sink=create_default_mcp_tool_invocation_log_sink(),
        audit_recorder=create_default_mcp_audit_recorder(settings.runtime.app_name, application_failures),
        metrics_recorder=metrics.recorder,
        metrics_server_factory=metrics.server_factory,
    )
