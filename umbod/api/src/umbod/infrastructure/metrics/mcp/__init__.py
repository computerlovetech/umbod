from importlib import import_module
from typing import Any

__all__ = [
    "ConfiguredMcpMetricsServerFactory",
    "McpMetricsHttpServer",
    "PrometheusMcpMetricsRecorder",
    "create_mcp_metrics",
    "create_metrics_app",
]

_EXPORTS: dict[str, str] = {
    "ConfiguredMcpMetricsServerFactory": ".composition",
    "McpMetricsHttpServer": ".http_server",
    "PrometheusMcpMetricsRecorder": ".prometheus",
    "create_mcp_metrics": ".composition",
    "create_metrics_app": ".http_server",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
