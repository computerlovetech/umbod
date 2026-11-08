from collections.abc import Iterable
from datetime import datetime, timezone
from typing import cast, get_args

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from pydantic import JsonValue

from umbod.core.telemetry import TelemetrySignal
from umbod.core.telemetry.analytics import LogWriteBatch
from umbod.core.telemetry.normalization.decoding import (
    DecodedAttribute, DecodedBoolean, DecodedInteger, DecodedInvalid, DecodedNumber, DecodedString,
    DecodedValue, ProducerKey,
)
from umbod.core.telemetry.normalization.evidence import (
    LEGACY_KEYS, attribute_text, bounded_text_evidence, capture_producer_evidence,
    schema_url_evidence, text_evidence,
)
from umbod.core.telemetry.normalization.mapping import normalize_log
from umbod.core.telemetry.normalization.models import CorrelationKey, InvalidValue, SourceEvidence, TimestampEvidence
from umbod.core.telemetry.analytics.projection import project_analytics_log
from umbod.rest.telemetry.validation import parse_message


_APPROVED_KEYS = frozenset((*get_args(ProducerKey), *get_args(CorrelationKey))) - frozenset(("trace_id", "span_id"))
_ERROR_INDICATOR_KEYS = frozenset(("error", "error.message"))
_INDICATOR_KEYS = frozenset(("mcp_server", "mcp_server_origin", "mcp.server.name")) | _ERROR_INDICATOR_KEYS
_RESOURCE_KEYS = frozenset(("service.name", "service.version"))


def normalize_analytics_logs(payload: dict[str, JsonValue], received_at: datetime) -> LogWriteBatch:
    request = cast(ExportLogsServiceRequest, parse_message(TelemetrySignal.LOGS, payload))
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = received_at.astimezone(timezone.utc) - epoch
    receipt_ns = (delta.days * 86400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1000
    records = []
    for resource in request.resource_logs:
        resource_attributes = _attributes(resource.resource.attributes, _RESOURCE_KEYS)
        for scope in resource.scope_logs:
            for record in scope.log_records:
                attributes = _attributes(record.attributes, _APPROVED_KEYS | frozenset(("event.name",)))
                source = SourceEvidence(
                    service=attribute_text(resource_attributes, "service.name"),
                    service_version=attribute_text(resource_attributes, "service.version"),
                    app_version=attribute_text(attributes, "app.version"),
                    scope_name=bounded_text_evidence(scope.scope.name), scope_version=bounded_text_evidence(scope.scope.version),
                    resource_schema_url=schema_url_evidence(resource.schema_url), scope_schema_url=schema_url_evidence(scope.schema_url),
                    record_event=text_evidence(record.event_name), semantic_event=attribute_text(attributes, "event.name"),
                    severity_text=text_evidence(record.severity_text), severity_number=record.severity_number if 0 <= record.severity_number <= 24 else InvalidValue(kind="invalid", reason="out_of_range"),
                )
                decoded = tuple(DecodedAttribute.model_validate({"key": key, "value": value}) for key, value in attributes.items() if key in _APPROVED_KEYS)
                decoded += tuple(DecodedAttribute.model_validate({"key": key, "value": DecodedString(kind="string", value=value.hex())}) for key, value in (("trace_id", record.trace_id), ("span_id", record.span_id)) if value)
                timestamps = TimestampEvidence(
                    source_ns=record.time_unix_nano, observed_ns=record.observed_time_unix_nano,
                    receipt_ns=receipt_ns,
                    effective_source="source" if record.time_unix_nano else "observed" if record.observed_time_unix_nano else "receipt",
                )
                records.append(project_analytics_log(normalize_log(source, timestamps, capture_producer_evidence(decoded))))
    return LogWriteBatch(records=tuple(records))


def _attributes(attributes: Iterable[KeyValue], approved: frozenset[str]) -> dict[str, DecodedValue]:
    return {attribute.key: _decode(attribute.key, attribute.value) for attribute in attributes if attribute.key in approved}


def _decode(key: str, value: AnyValue) -> DecodedValue:
    value_type = value.WhichOneof("value")
    if value_type == "string_value":
        if key in _ERROR_INDICATOR_KEYS:
            return DecodedBoolean(kind="boolean", value=True)
        if key in _INDICATOR_KEYS:
            return DecodedBoolean(kind="boolean", value=bool(value.string_value.strip()))
        if key not in LEGACY_KEYS and len(value.string_value) > 1024:
            return DecodedInvalid(kind="invalid", reason="oversize")
        return DecodedString(kind="string", value=value.string_value)
    if value_type == "bool_value":
        return DecodedBoolean(kind="boolean", value=value.bool_value) if key not in _INDICATOR_KEYS else DecodedInvalid(kind="invalid", reason="wrong_type")
    if value_type == "int_value":
        return DecodedInteger(kind="integer", value=value.int_value)
    if value_type == "double_value":
        return DecodedNumber(kind="number", value=value.double_value)
    return DecodedInvalid(kind="invalid", reason="wrong_type")
