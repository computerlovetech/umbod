from importlib import import_module
from typing import Any

__all__ = [
    "PrometheusCollectorMetrics",
    "create_collector_metrics_recorder",
    "create_receiver_app",
    "create_receiver_app_with_registry",
    "create_telemetry_app",
    "install_telemetry_receiver",
    "install_telemetry_receiver_with_registry",
]

_EXPORTS: dict[str, str] = {
    "PrometheusCollectorMetrics": ".prometheus",
    "create_collector_metrics_recorder": ".composition",
    "create_receiver_app": ".composition",
    "create_receiver_app_with_registry": ".composition",
    "create_telemetry_app": ".composition",
    "install_telemetry_receiver": ".composition",
    "install_telemetry_receiver_with_registry": ".composition",
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
