from importlib import import_module
from typing import Any

from umbod.mcp.telemetry.dependencies import McpTelemetryDependencies
from umbod.mcp.telemetry.ports import McpApplicationMetricsRecorder, McpMetricsServer, McpMetricsServerFactory

__all__ = ("create_configured_mcp_telemetry", "McpTelemetryDependencies", "McpApplicationMetricsRecorder", "McpMetricsServer", "McpMetricsServerFactory")


def __getattr__(name: str) -> Any:
    if name != "create_configured_mcp_telemetry":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(".composition", __name__), name)
    globals()[name] = value
    return value
