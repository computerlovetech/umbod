from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import cast

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import KeyValue
from opentelemetry.proto.logs.v1.logs_pb2 import LogRecord
from pydantic import JsonValue

from umbod.core.telemetry import TelemetrySignal
from umbod.core.telemetry.analytics import (
    AnalyticsLogRecord,
    DimensionGroup,
    LogDimension,
    LogWriteBatch,
    PresentDimensionValue,
    UnownedLog,
)
from umbod.rest.telemetry.validation import parse_message


_DIMENSION_ATTRIBUTES: dict[LogDimension, tuple[str, ...]] = {
    LogDimension.EVENT_NAME: ("event.name",),
    LogDimension.SESSION_ID: ("session.id", "session_id", "conversation.id", "conversation_id", "mcp.session.id"),
    LogDimension.TOOL_NAME: ("tool.name", "tool_name", "mcp.tool.name"),
}


def normalize_analytics_logs(
    payload: dict[str, JsonValue], received_at: datetime
) -> LogWriteBatch:
    request = cast(ExportLogsServiceRequest, parse_message(TelemetrySignal.LOGS, payload))
    records: list[AnalyticsLogRecord] = []
    for resource in request.resource_logs:
        resource_attributes = _string_attributes(resource.resource.attributes)
        for scope in resource.scope_logs:
            for record in scope.log_records:
                dimensions = _dimensions(record, resource_attributes)
                timestamp = record.time_unix_nano or record.observed_time_unix_nano
                occurred_at = (
                    datetime(1970, 1, 1, tzinfo=timezone.utc)
                    + timedelta(microseconds=timestamp // 1000)
                    if timestamp
                    else received_at
                )
                records.append(AnalyticsLogRecord(
                    occurred_at=occurred_at,
                    owner=UnownedLog(kind="unowned"),
                    dimensions=tuple(
                        DimensionGroup(
                            dimension=dimension,
                            value=PresentDimensionValue(kind="present", value=value),
                        )
                        for dimension, value in dimensions.items()
                    ),
                ))
    return LogWriteBatch(records=tuple(records))


def _string_attributes(attributes: Iterable[KeyValue]) -> dict[str, str]:
    values: dict[str, str] = {}
    for attribute in attributes:
        values.pop(attribute.key, None)
        if attribute.value.WhichOneof("value") == "string_value":
            values[attribute.key] = attribute.value.string_value
    return values


def _dimensions(record: LogRecord, resource: dict[str, str]) -> dict[LogDimension, str]:
    attributes = _string_attributes(record.attributes)
    dimensions: dict[LogDimension, str] = {}
    if "service.name" in resource:
        dimensions[LogDimension.SOURCE] = resource["service.name"]
    for dimension, keys in _DIMENSION_ATTRIBUTES.items():
        for key in keys:
            if key in attributes:
                dimensions[dimension] = attributes[key]
                break
    if record.event_name:
        dimensions[LogDimension.EVENT_NAME] = record.event_name
    if record.severity_text:
        dimensions[LogDimension.SEVERITY] = record.severity_text
    return dimensions
