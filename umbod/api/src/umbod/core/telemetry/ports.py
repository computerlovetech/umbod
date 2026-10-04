from typing import Protocol

from .models import TelemetryExport


class TelemetryUnavailable(Exception):
    pass


class TelemetrySink(Protocol):
    def export(self, batch: TelemetryExport) -> None: ...
