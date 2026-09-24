from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from umbod.mcp.logging.audit.event import (
    McpAnonymousAuditActor,
    McpAuditEvent,
    McpAuditOutcome,
    McpAuditRecord,
    McpAuditResult,
    McpAuditSuccess,
    McpAuthenticatedAuditActor,
    McpServerAuditTarget,
    McpToolAuditTarget,
    StructuredAttributeValue,
)


class McpAuditAttribute(StrEnum):
    STREAM = "mcp.audit.stream"
    ACTIVITY_TYPE = "mcp.audit.activity_type"
    OUTCOME = "mcp.audit.outcome"
    FAILURE_CATEGORY = "mcp.failure.category"
    ENDUSER_ID = "enduser.id"
    ACTOR_ANONYMOUS = "mcp.actor.anonymous"
    CLIENT_ID = "mcp.client.id"
    CLIENT_NAME = "mcp.client.name"
    SESSION_ID = "mcp.session.id"
    REQUEST_ID = "mcp.request.id"
    SERVER_NAME = "mcp.server.name"
    TOOL_NAME = "mcp.tool.name"
    CONNECTOR_ID = "mcp.connector.id"
    CONNECTOR_NAME = "mcp.connector.name"
    OPERATION_NAME = "mcp.operation.name"
    OCCURRED_AT_UNIX_NANO = "mcp.audit.occurred_at_unix_nano"
    CODE_HASH = "mcp.code.hash"


_CLIENT_ATTRIBUTE_NAMES: Mapping[str, McpAuditAttribute] = {
    "client_id": McpAuditAttribute.CLIENT_ID,
    "client_name": McpAuditAttribute.CLIENT_NAME,
    "session_id": McpAuditAttribute.SESSION_ID,
    "request_id": McpAuditAttribute.REQUEST_ID,
}

_TARGET_ATTRIBUTE_NAMES: Mapping[str, McpAuditAttribute] = {
    "connector_id": McpAuditAttribute.CONNECTOR_ID,
    "connector_name": McpAuditAttribute.CONNECTOR_NAME,
    "operation_name": McpAuditAttribute.OPERATION_NAME,
    "code_hash": McpAuditAttribute.CODE_HASH,
}


@dataclass(frozen=True)
class StructuredMcpAuditRecord:
    body: str
    severity_text: str
    attributes: Mapping[str, StructuredAttributeValue]
    trace_id: str
    span_id: str | None


class StructuredMcpAuditFormatter:
    def format_mcp_activity(self, event: McpAuditEvent) -> McpAuditRecord:
        return assemble_audit_record(event, map_audit_attributes(event))


def map_audit_attributes(event: McpAuditEvent) -> dict[str, StructuredAttributeValue]:
    attributes: dict[str, StructuredAttributeValue] = {
        McpAuditAttribute.STREAM: "mcp_audit",
        McpAuditAttribute.ACTIVITY_TYPE: _enum_value(event.activity_type),
        McpAuditAttribute.OUTCOME: _enum_value(event.outcome),
        McpAuditAttribute.OCCURRED_AT_UNIX_NANO: event.occurred_at_unix_nano,
    }
    attributes.update(_actor_attributes(event.actor))
    attributes.update(_client_attributes(event.client.attributes))
    attributes.update(_target_attributes(event.target))
    attributes.update(_result_attributes(event.result))
    return attributes


def assemble_audit_record(
    event: McpAuditEvent,
    attributes: Mapping[str, StructuredAttributeValue],
) -> StructuredMcpAuditRecord:
    return StructuredMcpAuditRecord(
        body="mcp audit event",
        severity_text=_severity_for(event.outcome),
        attributes=attributes,
        trace_id=event.correlation.trace_id,
        span_id=event.correlation.span_id,
    )


def _actor_attributes(
    actor: McpAnonymousAuditActor | McpAuthenticatedAuditActor,
) -> dict[str, StructuredAttributeValue]:
    if isinstance(actor, McpAuthenticatedAuditActor):
        return {
            McpAuditAttribute.ACTOR_ANONYMOUS: False,
            McpAuditAttribute.ENDUSER_ID: actor.authenticated_user_id,
        }
    return {McpAuditAttribute.ACTOR_ANONYMOUS: True}


def _client_attributes(values: Mapping[str, str]) -> dict[str, StructuredAttributeValue]:
    return {
        attribute: values[name]
        for name, attribute in _CLIENT_ATTRIBUTE_NAMES.items()
        if name in values
    }


def _target_attributes(
    target: McpServerAuditTarget | McpToolAuditTarget,
) -> dict[str, StructuredAttributeValue]:
    attributes: dict[str, StructuredAttributeValue] = {
        McpAuditAttribute.SERVER_NAME: target.server_name
    }
    if isinstance(target, McpToolAuditTarget):
        attributes[McpAuditAttribute.TOOL_NAME] = target.tool_name
        attributes.update(
            {
                attribute: target.attributes[name]
                for name, attribute in _TARGET_ATTRIBUTE_NAMES.items()
                if name in target.attributes
            }
        )
    return attributes


def _result_attributes(result: McpAuditResult) -> dict[str, StructuredAttributeValue]:
    if isinstance(result, McpAuditSuccess):
        return {}
    return {McpAuditAttribute.FAILURE_CATEGORY: _enum_value(result.failure_category)}


def _enum_value(value: StrEnum) -> str:
    return str(value.value)


def _severity_for(outcome: McpAuditOutcome) -> str:
    if outcome == McpAuditOutcome.FAILURE:
        return "ERROR"
    return "INFO"
