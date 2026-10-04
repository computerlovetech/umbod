import io
import json
import logging

import pytest
from pydantic import ValidationError

from umbod.core.telemetry import (
    TelemetryExport,
    TelemetrySignal,
    TelemetrySink,
    TelemetryUnavailable,
)
from umbod.core.telemetry.adapters import InMemoryTelemetrySink, StdoutTelemetrySink
from umbod.logging import StructuredLogRecord


@pytest.fixture
def structured_output(stdout_stream: io.StringIO) -> io.StringIO:
    return stdout_stream


def test_memory_sink_appends_only_nonempty_batches() -> None:
    adapter = InMemoryTelemetrySink(is_available=True)
    sink: TelemetrySink = adapter
    batch = TelemetryExport(
        signal=TelemetrySignal.LOGS, payload={"source": "preserved"}, item_count=1
    )
    sink.export(TelemetryExport(signal=TelemetrySignal.LOGS, payload={}, item_count=0))
    sink.export(batch)
    assert adapter.batches == [batch]


@pytest.mark.parametrize("item_count", [0, 1])
def test_unavailable_memory_sink_rejects_exports(item_count: int) -> None:
    sink: TelemetrySink = InMemoryTelemetrySink(is_available=False)
    with pytest.raises(TelemetryUnavailable):
        sink.export(
            TelemetryExport(
                signal=TelemetrySignal.LOGS, payload={}, item_count=item_count
            )
        )


def test_export_requires_all_fields_and_nonnegative_count() -> None:
    with pytest.raises(ValidationError):
        TelemetryExport(signal=TelemetrySignal.LOGS, payload={})
    with pytest.raises(ValidationError):
        TelemetryExport(signal=TelemetrySignal.LOGS, payload={}, item_count=-1)


def test_export_fields_are_immutable() -> None:
    batch = TelemetryExport(signal=TelemetrySignal.LOGS, payload={}, item_count=0)
    with pytest.raises(ValidationError):
        batch.item_count = 1


@pytest.mark.parametrize("signal", list(TelemetrySignal))
def test_stdout_sink_emits_structured_source_without_outer_trace(
    signal: TelemetrySignal, structured_output: io.StringIO
) -> None:
    sink: TelemetrySink = StdoutTelemetrySink()
    payload = {"timestamp": "18446744073709551615", "nested": {"traceId": "a" * 32}}
    sink.export(TelemetryExport(signal=signal, payload=payload, item_count=1))
    record = json.loads(structured_output.getvalue())
    assert record["body"] == "Telemetry export received"
    assert record["severity_text"] == "INFO"
    assert record["attributes"]["event.name"] == "umbod.telemetry.export"
    assert record["attributes"]["telemetry.signal"] == signal.value
    assert record["attributes"]["telemetry.payload"] == payload
    assert "trace_id" not in record and "span_id" not in record


def test_stdout_empty_export_emits_nothing(structured_output: io.StringIO) -> None:
    sink: TelemetrySink = StdoutTelemetrySink()
    sink.export(TelemetryExport(signal=TelemetrySignal.LOGS, payload={}, item_count=0))
    assert structured_output.getvalue() == ""


@pytest.mark.parametrize("item_count", [0, 1])
def test_stdout_filtered_info_is_unavailable(
    item_count: int, structured_output: io.StringIO
) -> None:
    logging.getLogger("umbod.structured").setLevel(logging.WARNING)
    sink: TelemetrySink = StdoutTelemetrySink()
    with pytest.raises(TelemetryUnavailable):
        sink.export(
            TelemetryExport(
                signal=TelemetrySignal.LOGS, payload={}, item_count=item_count
            )
        )
    assert structured_output.getvalue() == ""


def test_stdout_observable_emitter_failure_is_safe(
    monkeypatch: pytest.MonkeyPatch, structured_output: io.StringIO
) -> None:
    def fail(record: StructuredLogRecord) -> None:
        raise RuntimeError("private payload")

    monkeypatch.setattr(
        "umbod.core.telemetry.adapters.stdout.emit_structured_record", fail
    )
    sink: TelemetrySink = StdoutTelemetrySink()
    with pytest.raises(TelemetryUnavailable) as error:
        sink.export(
            TelemetryExport(
                signal=TelemetrySignal.LOGS, payload={"private": "data"}, item_count=1
            )
        )
    assert "private" not in str(error.value)
    assert structured_output.getvalue() == ""
