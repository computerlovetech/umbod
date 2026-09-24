from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


StructuredAttributeValue = str | int | float | bool


class McpAuditActivityType(StrEnum):
    CLIENT_CONNECTION = "client_connection"
    TOOL_DISCOVERY = "tool_discovery"
    TOOL_INVOCATION = "tool_invocation"


class McpAuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class McpAuditFailureCategory(StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    CONNECTOR_ERROR = "connector_error"
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass(frozen=True)
class McpAnonymousAuditActor:
    @property
    def anonymous(self) -> bool:
        return True

    @property
    def authenticated_user_id(self) -> str | None:
        return None


@dataclass(frozen=True)
class McpAuthenticatedAuditActor:
    authenticated_user_id: str

    @property
    def anonymous(self) -> bool:
        return False


McpAuditActorState = McpAnonymousAuditActor | McpAuthenticatedAuditActor


@dataclass(frozen=True)
class McpAuditClientMetadata:
    attributes: Mapping[str, str]

    @property
    def client_id(self) -> str | None:
        return self.attributes.get("client_id")

    @property
    def client_name(self) -> str | None:
        return self.attributes.get("client_name")

    @property
    def session_id(self) -> str | None:
        return self.attributes.get("session_id")

    @property
    def request_id(self) -> str | None:
        return self.attributes.get("request_id")


@dataclass(frozen=True)
class McpServerAuditTarget:
    server_name: str

    @property
    def tool_name(self) -> str | None:
        return None

    @property
    def connector_id(self) -> str | None:
        return None

    @property
    def connector_name(self) -> str | None:
        return None

    @property
    def operation_name(self) -> str | None:
        return None


@dataclass(frozen=True)
class McpToolAuditTarget:
    server_name: str
    tool_name: str
    attributes: Mapping[str, str]

    @property
    def connector_id(self) -> str | None:
        return self.attributes.get("connector_id")

    @property
    def connector_name(self) -> str | None:
        return self.attributes.get("connector_name")

    @property
    def operation_name(self) -> str | None:
        return self.attributes.get("operation_name")


McpAuditTargetState = McpServerAuditTarget | McpToolAuditTarget


@dataclass(frozen=True)
class McpAuditCorrelation:
    trace_id: str
    span_id: str | None


@dataclass(frozen=True)
class McpAuditSuccess:
    @property
    def outcome(self) -> McpAuditOutcome:
        return McpAuditOutcome.SUCCESS

    @property
    def failure_category(self) -> None:
        return None


@dataclass(frozen=True)
class McpAuditDenied:
    failure_category: McpAuditFailureCategory

    @property
    def outcome(self) -> McpAuditOutcome:
        return McpAuditOutcome.DENIED


@dataclass(frozen=True)
class McpAuditFailure:
    failure_category: McpAuditFailureCategory

    @property
    def outcome(self) -> McpAuditOutcome:
        return McpAuditOutcome.FAILURE


McpAuditResult = McpAuditSuccess | McpAuditDenied | McpAuditFailure


@dataclass(frozen=True)
class McpAuditEvent:
    activity_type: McpAuditActivityType
    actor: McpAuditActorState
    client: McpAuditClientMetadata
    target: McpAuditTargetState
    result: McpAuditResult
    occurred_at_unix_nano: int
    correlation: McpAuditCorrelation

    @property
    def outcome(self) -> McpAuditOutcome:
        return self.result.outcome

    @property
    def failure_category(self) -> McpAuditFailureCategory | None:
        return self.result.failure_category


@dataclass(frozen=True)
class McpAuditRecord:
    body: str
    severity_text: str
    attributes: Mapping[str, StructuredAttributeValue]
    trace_id: str
    span_id: str | None


class McpAuditEventSink(Protocol):
    def record_mcp_activity(self, event: McpAuditEvent) -> None: ...


class McpAuditFormatter(Protocol):
    def format_mcp_activity(self, event: McpAuditEvent) -> McpAuditRecord: ...
