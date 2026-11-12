import json
from datetime import datetime, timedelta, timezone

from pydantic import JsonValue

from .models import UsageKind, UsageOutcome, UsageRecord


_METHODS = {
    UsageKind.TOOL: 'tools/call',
    UsageKind.RESOURCE: 'resources/read',
    UsageKind.PROMPT: 'prompts/get',
}


def usage_occurred_at(record: UsageRecord) -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=record.occurred_at_unix_nano // 1000)


def usage_otel_payload(record: UsageRecord) -> dict[str, JsonValue]:
    severity_text, severity_number = ('WARNING', 13) if record.outcome == UsageOutcome.FAILURE else ('INFO', 9)
    attributes: list[JsonValue] = [
        {'key': key, 'value': {'stringValue': value}}
        for key, value in (
            ('event.name', 'umbod.mcp.usage'),
            ('event.id', str(record.event_id)),
            ('enduser.id', record.owner_id),
            ('mcp.method', _METHODS[record.kind]),
            ('mcp.usage.kind', record.kind.value),
            ('mcp.usage.outcome', record.outcome.value),
        )
    ]
    attributes.append({'key': 'mcp.usage.duration_ms', 'value': {'doubleValue': record.duration_ms}})
    log: dict[str, JsonValue] = {
        'timeUnixNano': str(record.occurred_at_unix_nano),
        'observedTimeUnixNano': str(record.observed_at_unix_nano),
        'severityText': severity_text,
        'severityNumber': severity_number,
        'body': {'stringValue': 'MCP usage observed'},
        'attributes': attributes,
    }
    if record.trace_id:
        log['traceId'] = record.trace_id
    if record.span_id and record.trace_id:
        log['spanId'] = record.span_id
    return {'resourceLogs': [{
        'resource': {'attributes': [{'key': 'service.name', 'value': {'stringValue': record.service_name}}]},
        'scopeLogs': [{'scope': {'name': 'umbod.mcp.usage', 'version': '1'}, 'logRecords': [log]}],
    }]}


def serialize_usage_otel(record: UsageRecord) -> str:
    return json.dumps(usage_otel_payload(record), separators=(',', ':'), ensure_ascii=False, allow_nan=False)
