from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from umbod.config import OtlpReceiverConfig
from umbod.core.signals import SignalPublisher
from umbod.core.telemetry import TelemetryExport, TelemetrySignal, TelemetrySink, TelemetryUnavailable
from umbod.core.telemetry.analytics import (
    ArchivedLogWriteBatch,
    LogOwnership,
    TelemetryAnalyticsUnavailable,
    TelemetryAnalyticsWriter,
)
from umbod.rest.telemetry.body import read_export_body
from umbod.rest.telemetry.dependencies import (
    authenticate_export,
    get_analytics_writer,
    get_raw_archive_enabled,
    get_receiver_config,
    get_telemetry_sink,
)
from umbod.rest.telemetry.errors import TelemetryHttpError
from umbod.rest.telemetry.normalization import normalize_analytics_logs
from umbod.rest.telemetry.observations import AcceptedCollectorLogs, get_accepted_logs_publisher
from umbod.rest.telemetry.responses import (
    JSON_MEDIA_TYPE,
    PROTOBUF_MEDIA_TYPE,
    export_media_type,
    export_success_response,
)
from umbod.rest.telemetry.validation import parse_export, parse_protobuf_export

router = APIRouter(prefix="/v1")


async def _deliver_export(
    signal: TelemetrySignal,
    request: Request,
    config: OtlpReceiverConfig,
    sink: TelemetrySink,
) -> tuple[TelemetryExport, str, bytes]:
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
    return batch, media_type, body


@router.post("/logs")
async def receive_logs(
    request: Request,
    owner: Annotated[LogOwnership, Depends(authenticate_export)],
    accepted_logs: Annotated[SignalPublisher[AcceptedCollectorLogs], Depends(get_accepted_logs_publisher)],
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
    analytics_writer: Annotated[TelemetryAnalyticsWriter, Depends(get_analytics_writer)],
    raw_archive_enabled: Annotated[bool, Depends(get_raw_archive_enabled)],
) -> Response:
    received_at = datetime.now(timezone.utc)
    batch, media_type, body = await _deliver_export(TelemetrySignal.LOGS, request, config, sink)
    if batch.item_count:
        normalized = normalize_analytics_logs(batch.payload, received_at, owner)
        write_batch = ArchivedLogWriteBatch(
            raw_payload=body,
            encoding="protobuf" if media_type == PROTOBUF_MEDIA_TYPE else "json",
            received_at=received_at,
            owner=owner,
            records=normalized.records,
        ) if raw_archive_enabled else normalized
        try:
            await analytics_writer.append_logs(write_batch)
        except TelemetryAnalyticsUnavailable:
            raise TelemetryHttpError(503, "Telemetry analytics is unavailable") from None
    accepted_logs.send(AcceptedCollectorLogs(batch.item_count))
    return export_success_response(media_type)


@router.post("/metrics")
async def receive_metrics(
    request: Request,
    owner: Annotated[LogOwnership, Depends(authenticate_export)],
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
) -> Response:
    _, media_type, _ = await _deliver_export(TelemetrySignal.METRICS, request, config, sink)
    return export_success_response(media_type)


@router.post("/traces")
async def receive_traces(
    request: Request,
    owner: Annotated[LogOwnership, Depends(authenticate_export)],
    config: Annotated[OtlpReceiverConfig, Depends(get_receiver_config)],
    sink: Annotated[TelemetrySink, Depends(get_telemetry_sink)],
) -> Response:
    _, media_type, _ = await _deliver_export(TelemetrySignal.TRACES, request, config, sink)
    return export_success_response(media_type)
