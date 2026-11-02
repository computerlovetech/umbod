from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from umbod.config import OtlpReceiverConfig
from umbod.core.telemetry import TelemetrySignal, TelemetrySink, TelemetryUnavailable
from umbod.core.telemetry.analytics import TelemetryAnalyticsUnavailable, TelemetryAnalyticsWriter
from umbod.rest.telemetry.body import read_export_body
from umbod.rest.telemetry.dependencies import (
    authenticate_export,
    get_analytics_writer,
    get_receiver_config,
    get_telemetry_sink,
)
from umbod.rest.telemetry.errors import TelemetryHttpError
from umbod.rest.telemetry.validation import parse_export
from umbod.rest.telemetry.normalization import normalize_analytics_logs

router = APIRouter(prefix="/v1", dependencies=[Depends(authenticate_export)])


async def _receive(
    signal: TelemetrySignal,
    request: Request,
    config: OtlpReceiverConfig,
    sink: TelemetrySink,
    analytics_writer: TelemetryAnalyticsWriter,
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
    if signal == TelemetrySignal.LOGS and batch.item_count:
        records = normalize_analytics_logs(batch.payload, datetime.now(timezone.utc))
        try:
            await analytics_writer.append_logs(records)
        except TelemetryAnalyticsUnavailable:
            raise TelemetryHttpError(503, "Telemetry analytics is unavailable") from None
    return JSONResponse(content={}, status_code=200)


@router.post("/logs")
async def receive_logs(
    request: Request,
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
    analytics_writer: Annotated[TelemetryAnalyticsWriter, Depends(get_analytics_writer)],
) -> JSONResponse:
    return await _receive(TelemetrySignal.LOGS, request, config, sink, analytics_writer)


@router.post("/metrics")
async def receive_metrics(
    request: Request,
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
    analytics_writer: Annotated[TelemetryAnalyticsWriter, Depends(get_analytics_writer)],
) -> JSONResponse:
    return await _receive(TelemetrySignal.METRICS, request, config, sink, analytics_writer)


@router.post("/traces")
async def receive_traces(
    request: Request,
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
    analytics_writer: Annotated[TelemetryAnalyticsWriter, Depends(get_analytics_writer)],
) -> JSONResponse:
    return await _receive(TelemetrySignal.TRACES, request, config, sink, analytics_writer)
