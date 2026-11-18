from importlib import import_module
from typing import Any

from umbod.rest.telemetry.metrics import CollectorMetricsRecorder
from umbod.rest.telemetry.observations import AcceptedCollectorLogs, CompletedCollectorRequest

__all__ = ["install_telemetry_receiver", "AcceptedCollectorLogs", "CollectorMetricsRecorder", "CompletedCollectorRequest"]


def __getattr__(name: str) -> Any:
    if name != "install_telemetry_receiver":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(".composition", __name__), name)
    globals()[name] = value
    return value
