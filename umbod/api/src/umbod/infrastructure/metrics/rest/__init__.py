from importlib import import_module
from typing import Any

__all__ = [
    "PrometheusRestMetricsRecorder",
    "RestMetricsHttpServer",
    "create_rest_metrics_app",
    "create_rest_metrics_http_server",
    "create_rest_metrics_recorder",
]

_EXPORTS: dict[str, str] = {
    "PrometheusRestMetricsRecorder": ".prometheus",
    "RestMetricsHttpServer": ".http_server",
    "create_rest_metrics_app": ".http_server",
    "create_rest_metrics_http_server": ".composition",
    "create_rest_metrics_recorder": ".composition",
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
