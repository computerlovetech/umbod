from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from umbod.config import OtlpReceiverConfig
from umbod.core.telemetry import TelemetrySignal, TelemetrySink, TelemetryUnavailable
from umbod.rest.telemetry.body import read_export_body
from umbod.rest.telemetry.dependencies import (
    authenticate_export,
    get_receiver_config,
    get_telemetry_sink,
)
from umbod.rest.telemetry.errors import TelemetryHttpError
from umbod.rest.telemetry.validation import parse_export

router = APIRouter(prefix="/v1", dependencies=[Depends(authenticate_export)])


async def _receive(
    signal: TelemetrySignal,
    request: Request,
    config: OtlpReceiverConfig,
    sink: TelemetrySink,
) -> JSONResponse:
    media_type = (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )
    if media_type != "application/json":
        raise TelemetryHttpError(415, "Only application/json telemetry is supported")
    body = await read_export_body(request, config.max_request_bytes)
    batch = parse_export(signal, body)
    try:
        sink.export(batch)
    except TelemetryUnavailable:
        raise TelemetryHttpError(503, "Telemetry logging is unavailable") from None
    return JSONResponse(content={}, status_code=200)


@router.post("/logs")
async def receive_logs(
    request: Request,
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
) -> JSONResponse:
    return await _receive(TelemetrySignal.LOGS, request, config, sink)


@router.post("/metrics")
async def receive_metrics(
    request: Request,
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
) -> JSONResponse:
    return await _receive(TelemetrySignal.METRICS, request, config, sink)


@router.post("/traces")
async def receive_traces(
    request: Request,
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
) -> JSONResponse:
    return await _receive(TelemetrySignal.TRACES, request, config, sink)
