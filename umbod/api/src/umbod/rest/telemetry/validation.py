from umbod.core.telemetry import TelemetryExport, TelemetrySignal
from umbod.core.telemetry.adapters.otlp_validation import (
    OtlpValidationError,
    parse_export as decode_json,
    parse_message as parse_message,
    parse_protobuf_export as decode_protobuf,
)

from .errors import TelemetryHttpError


def parse_export(signal: TelemetrySignal, body: bytes) -> TelemetryExport:
    try:
        return decode_json(signal, body)
    except OtlpValidationError as error:
        raise TelemetryHttpError(400, str(error)) from None


def parse_protobuf_export(signal: TelemetrySignal, body: bytes) -> TelemetryExport:
    try:
        return decode_protobuf(signal, body)
    except OtlpValidationError as error:
        raise TelemetryHttpError(400, str(error)) from None
