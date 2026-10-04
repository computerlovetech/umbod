import io
import json
import logging

import pytest

from umbod.core.telemetry import (
    TelemetryExport,
    TelemetrySignal,
    TelemetrySink,
    TelemetryUnavailable,
)
from umbod.core.telemetry.adapters import StdoutTelemetrySink


class RejectAllRecords(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return False


class BrokenStdout(io.StringIO):
    def write(self, value: str) -> int:
        raise BrokenPipeError("stdout unavailable")


@pytest.fixture
def batch() -> TelemetryExport:
    return TelemetryExport(
        signal=TelemetrySignal.LOGS,
        payload={
            "resourceLogs": [
                {"scopeLogs": [{"logRecords": [{"body": {"stringValue": "payload"}}]}]}
            ]
        },
        item_count=1,
    )


@pytest.fixture
def sink() -> TelemetrySink:
    return StdoutTelemetrySink()


def test_stdout_delivery_preserves_payload_without_internal_receipt(
    stdout_stream: io.StringIO, sink: TelemetrySink, batch: TelemetryExport
) -> None:
    sink.export(batch)
    record = json.loads(stdout_stream.getvalue())
    assert record["attributes"]["telemetry.payload"] == batch.payload
    assert record["resource"] == {"service.name": "ingestion-test"}
    assert "_umbod_stdout_delivery" not in stdout_stream.getvalue()


def test_handler_level_filtering_is_reported_as_unavailable(
    stdout_stream: io.StringIO, sink: TelemetrySink, batch: TelemetryExport
) -> None:
    logging.getLogger().handlers[0].setLevel(logging.WARNING)
    with pytest.raises(TelemetryUnavailable):
        sink.export(batch)
    assert stdout_stream.getvalue() == ""


def test_rejecting_handler_filter_is_reported_as_unavailable(
    stdout_stream: io.StringIO, sink: TelemetrySink, batch: TelemetryExport
) -> None:
    logging.getLogger().handlers[0].addFilter(RejectAllRecords())
    with pytest.raises(TelemetryUnavailable):
        sink.export(batch)
    assert stdout_stream.getvalue() == ""


def test_rejecting_logger_filter_is_reported_as_unavailable(
    stdout_stream: io.StringIO, sink: TelemetrySink, batch: TelemetryExport
) -> None:
    logging.getLogger("umbod.structured").addFilter(RejectAllRecords())
    with pytest.raises(TelemetryUnavailable):
        sink.export(batch)
    assert stdout_stream.getvalue() == ""


def test_broken_stdout_is_reported_as_unavailable(
    stdout_stream: io.StringIO, sink: TelemetrySink, batch: TelemetryExport
) -> None:
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(BrokenStdout())
    with pytest.raises(TelemetryUnavailable):
        sink.export(batch)
    assert stdout_stream.getvalue() == ""


def test_info_level_disabled_is_reported_as_unavailable(
    stdout_stream: io.StringIO, sink: TelemetrySink, batch: TelemetryExport
) -> None:
    logging.getLogger().setLevel(logging.WARNING)
    with pytest.raises(TelemetryUnavailable):
        sink.export(batch)
    assert stdout_stream.getvalue() == ""
