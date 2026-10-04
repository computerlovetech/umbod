from ..models import TelemetryExport
from ..ports import TelemetryUnavailable


class InMemoryTelemetrySink:
    def __init__(self, is_available: bool) -> None:
        self.is_available = is_available
        self.batches: list[TelemetryExport] = []

    def export(self, batch: TelemetryExport) -> None:
        if not self.is_available:
            raise TelemetryUnavailable("Telemetry sink unavailable")
        if batch.item_count:
            self.batches.append(batch)
