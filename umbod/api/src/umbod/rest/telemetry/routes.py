from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

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
from umbod.rest.telemetry.responses import (
    JSON_MEDIA_TYPE,
    PROTOBUF_MEDIA_TYPE,
    export_media_type,
    export_success_response,
)
from umbod.rest.telemetry.validation import parse_export, parse_protobuf_export
from umbod.rest.telemetry.normalization import normalize_analytics_logs

router = APIRouter(prefix="/v1", dependencies=[Depends(authenticate_export)])


async def _receive(
    signal: TelemetrySignal,
    request: Request,
    config: OtlpReceiverConfig,
    sink: TelemetrySink,
    analytics_writer: TelemetryAnalyticsWriter,
) -> Response:
    media_type = export_media_type(request)
    if media_type not in {JSON_MEDIA_TYPE, PROTOBUF_MEDIA_TYPE}:
        raise TelemetryHttpError(415, "Unsupported telemetry media type")
    body = await read_export_body(request, config.max_request_bytes)
    parser = parse_protobuf_export if media_type == PROTOBUF_MEDIA_TYPE else parse_export
    batch = parser(signal, body)
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
    return export_success_response(media_type)


@router.post("/logs")
async def receive_logs(
    request: Request,
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
    analytics_writer: Annotated[TelemetryAnalyticsWriter, Depends(get_analytics_writer)],
) -> Response:
    return await _receive(TelemetrySignal.LOGS, request, config, sink, analytics_writer)


@router.post("/metrics")
async def receive_metrics(
    request: Request,
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
    analytics_writer: Annotated[TelemetryAnalyticsWriter, Depends(get_analytics_writer)],
) -> Response:
    return await _receive(TelemetrySignal.METRICS, request, config, sink, analytics_writer)


@router.post("/traces")
async def receive_traces(
    request: Request,
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
    analytics_writer: Annotated[TelemetryAnalyticsWriter, Depends(get_analytics_writer)],
) -> Response:
    return await _receive(TelemetrySignal.TRACES, request, config, sink, analytics_writer)
