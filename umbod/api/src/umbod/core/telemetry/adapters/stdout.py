import logging

from umbod.logging import StructuredLogRecord
from umbod.logging import emit_structured_record_to_stdout as emit_structured_record

from ..models import TelemetryExport
from ..ports import TelemetryUnavailable


class StdoutTelemetrySink:
    def export(self, batch: TelemetryExport) -> None:
        if not logging.getLogger("umbod.structured").isEnabledFor(logging.INFO):
            raise TelemetryUnavailable("Telemetry sink unavailable")
        if not batch.item_count:
            return
        record = StructuredLogRecord(
            body="Telemetry export received",
            severity_text="INFO",
            attributes={
                "event.name": "umbod.telemetry.export",
                "telemetry.signal": batch.signal.value,
                "telemetry.payload": batch.payload,
            },
            trace_id=None,
            span_id=None,
        )
        try:
            emit_structured_record(record)
        except Exception:
            raise TelemetryUnavailable("Telemetry sink unavailable") from None
