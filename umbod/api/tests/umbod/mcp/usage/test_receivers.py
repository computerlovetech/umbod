import math

import pytest

from umbod.mcp.usage.ports import NoUsageCorrelation
from umbod.core.usage.models import UsageKind, UsageOwner, UsageRecord
from umbod.core.usage.otel import serialize_usage_otel
from umbod.mcp.signals.capabilities import (
    McpCapabilityCompleted, McpCapabilityMethod, McpCapabilitySucceeded, prompt_target,
)
from umbod.mcp.signals.events import (
    McpInteractionType, McpInvocationActor, McpInvocationCorrelation,
    McpToolIdentity, McpToolInvocationStarted, McpToolInvocationSucceeded,
)
from umbod.mcp.usage.receivers import CapabilityUsageReceiver, InvocationUsageReceiver, UsageCompletionProjection


class AdmissionCollector:
    def __init__(self) -> None:
        self.records: list[UsageRecord] = []
        self.failures = 0

    def enqueue(self, record: UsageRecord) -> None:
        self.records.append(record)

    def projection_failed(self) -> None:
        self.failures += 1


@pytest.fixture
def admission() -> AdmissionCollector:
    return AdmissionCollector()


@pytest.fixture
def actor() -> McpInvocationActor:
    return McpInvocationActor(authenticated_user_id='SECRET audit identity',
                              usage_owner=UsageOwner(kind='owned', owner_id='a' * 64))


@pytest.mark.parametrize('name,connector_id,count', [
    ('search_tools', None, 0), ('execute_tool', None, 0), ('execute_code', None, 0),
    ('execute_tool', 'connector', 1), ('built_in', None, 1),
])
def test_wrappers_are_excluded_but_nested_and_builtin_tools_count(
    admission: AdmissionCollector, actor: McpInvocationActor, name: str, connector_id: str | None, count: int,
) -> None:
    receiver = InvocationUsageReceiver(UsageCompletionProjection(admission, 'test', lambda: 999))
    event = McpToolInvocationSucceeded(McpToolInvocationStarted(
        McpInteractionType.TOOL_INVOCATION, McpToolIdentity(name, connector_id, None), actor, 100,
    ), 2.5)
    receiver(event)
    assert len(admission.records) == count
    if count:
        assert admission.records[0].occurred_at_unix_nano == 2_500_100
        assert admission.records[0].observed_at_unix_nano == 999
        assert 'SECRET' not in serialize_usage_otel(admission.records[0])
        assert name not in serialize_usage_otel(admission.records[0])


@pytest.mark.parametrize('method,kind', [
    (McpCapabilityMethod.READ_RESOURCE, UsageKind.RESOURCE),
    (McpCapabilityMethod.GET_PROMPT, UsageKind.PROMPT),
    (McpCapabilityMethod.LIST_RESOURCES, None),
    (McpCapabilityMethod.LIST_RESOURCE_TEMPLATES, None),
    (McpCapabilityMethod.LIST_PROMPTS, None),
])
def test_only_resource_reads_and_prompt_retrievals_are_collected(
    admission: AdmissionCollector, actor: McpInvocationActor, method: McpCapabilityMethod, kind: UsageKind | None,
) -> None:
    receiver = CapabilityUsageReceiver(UsageCompletionProjection(admission, 'test', lambda: 999))
    receiver(McpCapabilityCompleted(method, prompt_target('SECRET prompt'), McpCapabilitySucceeded(),
                                    1, McpInvocationCorrelation('f' * 32, 'e' * 16), actor, 100))
    assert [record.kind for record in admission.records] == ([kind] if kind is not None else [])
    assert 'SECRET' not in repr(admission.records)


def test_bare_audit_identity_is_not_an_ownership_authority(admission: AdmissionCollector) -> None:
    projection = UsageCompletionProjection(admission, 'test', lambda: 999)
    projection.completed(McpInvocationActor(authenticated_user_id='user'), 100, 1, NoUsageCorrelation(), UsageKind.TOOL, 'success')
    assert admission.records == []
    assert admission.failures == 0


@pytest.mark.parametrize('trace,span,expected_trace,expected_span', [
    ('a' * 32, 'b' * 16, 'a' * 32, 'b' * 16),
    ('SECRET', 'b' * 16, '', ''), ('0' * 32, 'b' * 16, '', ''),
    ('a' * 32, '0' * 16, 'a' * 32, ''), ('a' * 32, 'SECRET', 'a' * 32, ''),
])
def test_correlation_is_bounded_valid_or_empty(
    admission: AdmissionCollector, actor: McpInvocationActor,
    trace: str, span: str, expected_trace: str, expected_span: str,
) -> None:
    projection = UsageCompletionProjection(admission, 'test', lambda: 999)
    projection.completed(actor, 100, 1, McpInvocationCorrelation(trace, span), UsageKind.TOOL, 'success')
    assert admission.records[0].trace_id == expected_trace
    assert admission.records[0].span_id == expected_span


@pytest.mark.parametrize('duration', [math.nan, math.inf, -math.inf])
def test_nonfinite_duration_is_dropped_as_projection_failure(
    admission: AdmissionCollector, actor: McpInvocationActor, duration: float,
) -> None:
    projection = UsageCompletionProjection(admission, 'test', lambda: 999)
    projection.completed(actor, 100, duration, NoUsageCorrelation(), UsageKind.TOOL, 'success')
    assert admission.records == []
    assert admission.failures == 1


def test_negative_duration_is_normalized_to_zero(admission: AdmissionCollector, actor: McpInvocationActor) -> None:
    projection = UsageCompletionProjection(admission, 'test', lambda: 999)
    projection.completed(actor, 100, -1, NoUsageCorrelation(), UsageKind.TOOL, 'failure')
    assert admission.records[0].duration_ms == 0
    assert admission.records[0].occurred_at_unix_nano == 100
