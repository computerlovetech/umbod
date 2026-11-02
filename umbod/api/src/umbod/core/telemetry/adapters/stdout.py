import logging

from umbod.logging import emit_telemetry_export_to_stdout

from ..models import TelemetryExport
from ..ports import TelemetryUnavailable


class StdoutTelemetrySink:
    def export(self, batch: TelemetryExport) -> None:
        if not logging.getLogger("umbod.structured").isEnabledFor(logging.INFO):
            raise TelemetryUnavailable("Telemetry sink unavailable")
        if not batch.item_count:
            return
        try:
            emit_telemetry_export_to_stdout(batch)
        except Exception:
            raise TelemetryUnavailable("Telemetry sink unavailable") from None
