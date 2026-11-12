from collections.abc import Callable

from umbod.core.invocation.failure_evidence import InvocationExceptionEvidence
from umbod.logging import StructuredLogRecord
from umbod.mcp.signals.capabilities import (
    McpCapabilityCancelled,
    McpCapabilityCompleted,
    McpCapabilityFailed,
    McpCapabilityFailureCategory,
    McpCapabilityMethod,
    McpPromptTarget,
    McpResourceTarget,
)


class CapabilityLoggingReceiver:
    def __init__(self, write_record: Callable[[StructuredLogRecord], None]) -> None:
        self._write_record = write_record

    def __call__(self, event: McpCapabilityCompleted) -> None:
        self._write_record(format_capability_completed(event))


def format_capability_completed(event: McpCapabilityCompleted) -> StructuredLogRecord:
    attributes: dict[str, str | int | float | bool] = {
        'mcp.interaction.type': _INTERACTION_TYPES[event.method],
        'mcp.method': event.method.value,
        'mcp.capability.outcome': event.outcome.value,
        'mcp.capability.duration_ms': event.duration_ms,
    }
    if isinstance(event.target, McpResourceTarget):
        attributes['mcp.resource.uri_hash'] = event.target.uri_fingerprint
    if isinstance(event.target, McpPromptTarget):
        attributes['mcp.prompt.name_hash'] = event.target.name_fingerprint
    for key, value in (
        ('enduser.id', event.actor.authenticated_user_id),
        ('mcp.client.id', event.actor.agent_client_id),
        ('mcp.session.id', event.actor.session_id),
    ):
        if value is not None:
            attributes[key] = value
    severity = 'INFO'
    result = event.result
    if isinstance(result, McpCapabilityFailed):
        attributes['mcp.failure.category'] = result.category.value
        severity = 'ERROR' if result.category == McpCapabilityFailureCategory.UNEXPECTED_ERROR else 'WARNING'
    if isinstance(result, (McpCapabilityFailed, McpCapabilityCancelled)):
        attributes['mcp.failure.origin'] = result.evidence.origin.value
        if isinstance(result.evidence, InvocationExceptionEvidence):
            attributes['exception.type'] = result.evidence.exception_type
            attributes['exception.stacktrace'] = result.evidence.stacktrace
    return StructuredLogRecord(
        body='mcp capability operation completed',
        severity_text=severity,
        attributes=attributes,
        trace_id=event.correlation.trace_id,
        span_id=event.correlation.span_id,
    )


_INTERACTION_TYPES = {
    McpCapabilityMethod.READ_RESOURCE: 'resource_read',
    McpCapabilityMethod.GET_PROMPT: 'prompt_get',
    McpCapabilityMethod.LIST_RESOURCES: 'resource_list',
    McpCapabilityMethod.LIST_RESOURCE_TEMPLATES: 'resource_template_list',
    McpCapabilityMethod.LIST_PROMPTS: 'prompt_list',
}
