from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Protocol, Self

from umbod.mcp.logging.invocation.event import (
    McpToolInvocationFailed,
    McpToolInvocationLogEvent,
    McpToolInvocationOutcome,
)


StructuredAttributeValue = str | int | float | bool


class McpToolInvocationLogAttribute(StrEnum):
    INTERACTION_TYPE = "mcp.interaction.type"
    TOOL_NAME = "mcp.tool.name"
    CONNECTOR_ID = "mcp.connector.id"
    CONNECTOR_NAME = "mcp.connector.name"
    OPERATION_NAME = "mcp.operation.name"
    INVOCATION_OUTCOME = "mcp.invocation.outcome"
    INVOCATION_DURATION_MS = "mcp.invocation.duration_ms"
    FAILURE_CATEGORY = "mcp.failure.category"
    ENDUSER_ID = "enduser.id"
    CLIENT_ID = "mcp.client.id"
    SESSION_ID = "mcp.session.id"


class McpToolInvocationLogRecord(Protocol):
    body: str
    severity_text: str
    attributes: Mapping[str, StructuredAttributeValue]
    trace_id: str | None
    span_id: str | None


@dataclass(frozen=True)
class StructuredLogRecord:
    body: str
    severity_text: str
    attributes: Mapping[str, StructuredAttributeValue]
    trace_id: str | None = None
    span_id: str | None = None


class McpToolInvocationLogFormatter(Protocol):
    def format_invocation_completed(
        self, event: McpToolInvocationLogEvent
    ) -> McpToolInvocationLogRecord: ...


class StructuredMcpToolInvocationLogFormatter:
    def format_invocation_completed(self, event: McpToolInvocationLogEvent) -> StructuredLogRecord:
        return assemble_invocation_log_record(event, map_invocation_attributes(event))


def map_invocation_attributes(
    event: McpToolInvocationLogEvent,
) -> dict[str, StructuredAttributeValue]:
    builder = _InvocationLogAttributesBuilder(event)
    optional_attributes = (
        (McpToolInvocationLogAttribute.CONNECTOR_ID, event.started.tool.connector_id),
        (
            McpToolInvocationLogAttribute.CONNECTOR_NAME,
            event.started.tool.connector_name or event.started.tool.connector_id,
        ),
        (McpToolInvocationLogAttribute.OPERATION_NAME, event.started.tool.operation_name),
        (McpToolInvocationLogAttribute.ENDUSER_ID, event.started.actor.authenticated_user_id),
        (McpToolInvocationLogAttribute.CLIENT_ID, event.started.actor.agent_client_id),
        (McpToolInvocationLogAttribute.SESSION_ID, event.started.actor.session_id),
    )
    for key, value in optional_attributes:
        if value is not None:
            builder.with_attribute(key, value)
    return builder.with_failure(event).build()


def assemble_invocation_log_record(
    event: McpToolInvocationLogEvent,
    attributes: Mapping[str, StructuredAttributeValue],
) -> StructuredLogRecord:
    correlation = getattr(event.started, "correlation", None)
    return StructuredLogRecord(
        body="mcp tool invocation completed",
        severity_text=_severity_for(_enum_value(event.outcome)),
        attributes=attributes,
        trace_id=correlation.trace_id if correlation is not None else None,
        span_id=correlation.span_id if correlation is not None else None,
    )


class _InvocationLogAttributesBuilder:
    def __init__(self, event: McpToolInvocationLogEvent) -> None:
        self._attributes: dict[str, StructuredAttributeValue] = {
            McpToolInvocationLogAttribute.INTERACTION_TYPE: _enum_value(
                event.started.interaction_type
            ),
            McpToolInvocationLogAttribute.TOOL_NAME: event.started.tool.tool_name,
            McpToolInvocationLogAttribute.INVOCATION_OUTCOME: _enum_value(event.outcome),
            McpToolInvocationLogAttribute.INVOCATION_DURATION_MS: event.duration_ms,
        }

    def with_attribute(
        self, key: McpToolInvocationLogAttribute, value: StructuredAttributeValue
    ) -> Self:
        self._attributes[key] = value
        return self

    def with_failure(self, event: McpToolInvocationLogEvent) -> Self:
        if isinstance(event, McpToolInvocationFailed):
            self._attributes[McpToolInvocationLogAttribute.FAILURE_CATEGORY] = _enum_value(
                event.failure_category
            )
        return self

    def build(self) -> dict[str, StructuredAttributeValue]:
        return self._attributes


def _enum_value(value: StrEnum) -> str:
    return str(value.value)


def _severity_for(outcome: str) -> str:
    if outcome == McpToolInvocationOutcome.FAILURE:
        return "ERROR"
    return "INFO"
