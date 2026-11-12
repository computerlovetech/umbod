import json
from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from umbod.core.usage import UsageKind, UsageOutcome, UsageRecord, serialize_usage_otel, usage_occurred_at


def record(kind: UsageKind, outcome: UsageOutcome) -> UsageRecord:
    return UsageRecord(
        event_id=UUID('11111111-1111-4111-8111-111111111111'), owner_id='a' * 64,
        occurred_at_unix_nano=1704067200123456789, observed_at_unix_nano=1704067200999999999,
        kind=kind, outcome=outcome, duration_ms=12.5, service_name='umbod-mcp',
        trace_id='b' * 32, span_id='c' * 16,
    )


@pytest.mark.parametrize(('kind', 'method'), [
    (UsageKind.TOOL, 'tools/call'),
    (UsageKind.RESOURCE, 'resources/read'),
    (UsageKind.PROMPT, 'prompts/get'),
])
@pytest.mark.parametrize('outcome', tuple(UsageOutcome))
def test_usage_serializes_as_correlated_otlp_logs(kind: UsageKind, method: str, outcome: UsageOutcome) -> None:
    usage = record(kind, outcome)

    encoded = serialize_usage_otel(usage)
    resource_logs = json.loads(encoded)['resourceLogs'][0]
    scope_logs = resource_logs['scopeLogs'][0]
    log = scope_logs['logRecords'][0]
    attributes = {attribute['key']: attribute['value'] for attribute in log['attributes']}

    assert resource_logs['resource']['attributes'] == [{'key': 'service.name', 'value': {'stringValue': 'umbod-mcp'}}]
    assert scope_logs['scope'] == {'name': 'umbod.mcp.usage', 'version': '1'}
    assert log['timeUnixNano'] == str(usage.occurred_at_unix_nano)
    assert log['observedTimeUnixNano'] == str(usage.observed_at_unix_nano)
    assert log['traceId'] == usage.trace_id
    assert log['spanId'] == usage.span_id
    assert attributes['event.name'] == {'stringValue': 'umbod.mcp.usage'}
    assert attributes['event.id'] == {'stringValue': str(usage.event_id)}
    assert attributes['enduser.id'] == {'stringValue': usage.owner_id}
    assert attributes['mcp.method'] == {'stringValue': method}
    assert attributes['mcp.usage.kind'] == {'stringValue': kind.value}
    assert attributes['mcp.usage.outcome'] == {'stringValue': outcome.value}
    assert attributes['mcp.usage.duration_ms'] == {'doubleValue': 12.5}
    assert len(encoded.encode('utf-8')) < 2048
    assert serialize_usage_otel(usage) == encoded


def test_usage_without_correlation_omits_trace_and_span_fields() -> None:
    usage = record(UsageKind.TOOL, UsageOutcome.SUCCESS).model_copy(update={'trace_id': '', 'span_id': ''})

    log = json.loads(serialize_usage_otel(usage))['resourceLogs'][0]['scopeLogs'][0]['logRecords'][0]

    assert 'traceId' not in log
    assert 'spanId' not in log


def test_usage_timestamp_uses_integer_precision_at_utc_boundary() -> None:
    usage = record(UsageKind.TOOL, UsageOutcome.SUCCESS)

    assert usage_occurred_at(usage) == datetime(2024, 1, 1, 0, 0, 0, 123456, tzinfo=timezone.utc)


@pytest.mark.parametrize('duration', [-1.0, float('nan'), float('inf')])
def test_invalid_duration_cannot_enter_usage_records(duration: float) -> None:
    payload = record(UsageKind.TOOL, UsageOutcome.SUCCESS).model_dump()
    payload['duration_ms'] = duration

    with pytest.raises(ValidationError):
        UsageRecord.model_validate(payload)


def test_usage_contract_rejects_arbitrary_payload_fields() -> None:
    payload = record(UsageKind.TOOL, UsageOutcome.SUCCESS).model_dump()
    payload['arguments'] = {'credential': 'private-token'}

    with pytest.raises(ValidationError):
        UsageRecord.model_validate(payload)
