import json

import pytest

from umbod.core.invocation.failure_evidence import InvocationExceptionEvidence, InvocationFailureOrigin, InvocationRejectedFailure
from umbod.logging import StructuredLogRecord, format_structured_record
from umbod.mcp.listeners.capability_logging import CapabilityLoggingReceiver
from umbod.mcp.signals.capabilities import (
    McpCapabilityCancelled,
    McpCapabilityCompleted,
    McpCapabilityDiscoveryTarget,
    McpCapabilityFailed,
    McpCapabilityFailureCategory,
    McpCapabilityMethod,
    McpCapabilityResult,
    McpCapabilitySucceeded,
    McpCapabilityTarget,
    prompt_target,
    resource_target,
)
from umbod.mcp.signals.events import McpInvocationActor, McpInvocationCorrelation


def completion(
    method: McpCapabilityMethod, target: McpCapabilityTarget, result: McpCapabilityResult,
) -> McpCapabilityCompleted:
    return McpCapabilityCompleted(
        method=method, target=target, result=result, duration_ms=12.5,
        correlation=McpInvocationCorrelation('a' * 32, 'b' * 16),
        actor=McpInvocationActor('user-id', 'client-id', 'session-id'),
        started_at_unix_nano=123,
    )


@pytest.mark.parametrize(('method', 'target', 'interaction'), [
    (McpCapabilityMethod.READ_RESOURCE, resource_target('private://secret-target'), 'resource_read'),
    (McpCapabilityMethod.GET_PROMPT, prompt_target('secret-prompt'), 'prompt_get'),
    (McpCapabilityMethod.LIST_RESOURCES, McpCapabilityDiscoveryTarget(), 'resource_list'),
    (McpCapabilityMethod.LIST_RESOURCE_TEMPLATES, McpCapabilityDiscoveryTarget(), 'resource_template_list'),
    (McpCapabilityMethod.LIST_PROMPTS, McpCapabilityDiscoveryTarget(), 'prompt_list'),
])
def test_receiver_writes_one_correlated_capability_record_without_tool_fields(
    method: McpCapabilityMethod, target: McpCapabilityTarget, interaction: str,
) -> None:
    records: list[StructuredLogRecord] = []
    receiver = CapabilityLoggingReceiver(records.append)

    receiver(completion(method, target, McpCapabilitySucceeded()))

    assert len(records) == 1
    record = records[0]
    assert record.body == 'mcp capability operation completed'
    assert record.severity_text == 'INFO'
    assert record.trace_id == 'a' * 32
    assert record.span_id == 'b' * 16
    assert record.attributes['mcp.method'] == method.value
    assert record.attributes['mcp.interaction.type'] == interaction
    assert record.attributes['mcp.capability.outcome'] == 'success'
    assert record.attributes['mcp.capability.duration_ms'] == 12.5
    assert record.attributes['enduser.id'] == 'user-id'
    assert record.attributes['mcp.client.id'] == 'client-id'
    assert record.attributes['mcp.session.id'] == 'session-id'
    assert 'mcp.tool.name' not in record.attributes
    assert 'mcp.connector.id' not in record.attributes
    serialized = format_structured_record('test', record)
    assert 'secret-target' not in serialized
    assert 'secret-prompt' not in serialized
    payload = json.loads(serialized)
    assert payload['trace_id'] == record.trace_id
    assert payload['attributes']['mcp.method'] == method.value


@pytest.mark.parametrize('category', [
    McpCapabilityFailureCategory.AUTHORIZATION,
    McpCapabilityFailureCategory.VALIDATION,
    McpCapabilityFailureCategory.NOT_FOUND,
])
def test_expected_rejections_are_warnings_without_exception_frames(category: McpCapabilityFailureCategory) -> None:
    records: list[StructuredLogRecord] = []
    receiver = CapabilityLoggingReceiver(records.append)

    receiver(completion(
        McpCapabilityMethod.READ_RESOURCE, resource_target('private://secret-target'),
        McpCapabilityFailed(category, InvocationRejectedFailure(InvocationFailureOrigin.CLIENT_INPUT)),
    ))

    assert len(records) == 1
    record = records[0]
    assert record.severity_text == 'WARNING'
    assert record.attributes['mcp.capability.outcome'] == 'failure'
    assert record.attributes['mcp.failure.category'] == category.value
    assert record.attributes['mcp.failure.origin'] == 'client_input'
    assert 'exception.stacktrace' not in record.attributes


def test_unexpected_failure_is_error_with_sanitized_exception_evidence() -> None:
    records: list[StructuredLogRecord] = []
    receiver = CapabilityLoggingReceiver(records.append)

    receiver(completion(
        McpCapabilityMethod.GET_PROMPT, prompt_target('secret-prompt'),
        McpCapabilityFailed(
            McpCapabilityFailureCategory.UNEXPECTED_ERROR,
            InvocationExceptionEvidence(InvocationFailureOrigin.INTERNAL, 'RuntimeError', 'RuntimeError: [message omitted]'),
        ),
    ))

    assert len(records) == 1
    record = records[0]
    assert record.severity_text == 'ERROR'
    assert record.attributes['exception.type'] == 'RuntimeError'
    assert record.attributes['exception.stacktrace'] == 'RuntimeError: [message omitted]'
    assert record.attributes['mcp.failure.origin'] == 'internal'


def test_cancellation_is_distinct_from_success_and_failure() -> None:
    records: list[StructuredLogRecord] = []
    receiver = CapabilityLoggingReceiver(records.append)

    receiver(completion(
        McpCapabilityMethod.READ_RESOURCE, resource_target('private://secret-target'),
        McpCapabilityCancelled(InvocationExceptionEvidence(
            InvocationFailureOrigin.INTERNAL, 'CancelledError', 'CancelledError: [message omitted]',
        )),
    ))

    assert len(records) == 1
    assert records[0].attributes['mcp.capability.outcome'] == 'cancelled'
    assert records[0].severity_text == 'INFO'
    assert 'mcp.failure.category' not in records[0].attributes
