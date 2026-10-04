import hmac
from typing import Annotated

from fastapi import Depends, Request

from umbod.config import OtlpReceiverConfig
from umbod.core.telemetry import TelemetrySink
from umbod.core.telemetry.adapters import StdoutTelemetrySink
from umbod.rest.telemetry.errors import TelemetryHttpError


def get_receiver_config() -> OtlpReceiverConfig:
    raise RuntimeError("OTLP receiver configuration is not installed")


def get_telemetry_sink() -> TelemetrySink:
    return StdoutTelemetrySink()


def authenticate_export(
    request: Request,
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
) -> None:
    if not config.enabled:
        raise TelemetryHttpError(503, "Telemetry ingestion is disabled")
    if config.allow_unauthenticated:
        return
    if not config.bearer_token:
        raise TelemetryHttpError(503, "Telemetry authentication is not configured")
    authorization_values = request.headers.getlist("authorization")
    if len(authorization_values) != 1:
        raise TelemetryHttpError(401, "Bearer authentication is required")
    scheme, separator, token = authorization_values[0].partition(" ")
    if scheme.lower() != "bearer" or not separator or not token:
        raise TelemetryHttpError(401, "Bearer authentication is required")
    if not hmac.compare_digest(
        token.encode("utf-8"), config.bearer_token.encode("utf-8")
    ):
        raise TelemetryHttpError(401, "Invalid bearer credentials")
