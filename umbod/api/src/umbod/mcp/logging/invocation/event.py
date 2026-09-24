from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol


class McpInteractionType(StrEnum):
    TOOL_INVOCATION = "tool_invocation"


class McpToolInvocationOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class McpToolInvocationFailureCategory(StrEnum):
    VALIDATION = "validation"
    AUTHORIZATION = "authorization"
    CONNECTOR_ERROR = "connector_error"
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass(frozen=True)
class McpToolIdentity:
    tool_name: str
    connector_id: str | None
    operation_name: str | None
    connector_name: str | None = None


@dataclass(frozen=True)
class McpInvocationActor:
    authenticated_user_id: str | None = None
    agent_client_id: str | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class McpInvocationCorrelation:
    trace_id: str
    span_id: str | None = None


@dataclass(frozen=True)
class McpToolInvocationStarted:
    interaction_type: McpInteractionType
    tool: McpToolIdentity
    actor: McpInvocationActor
    started_at_unix_nano: int
    correlation: McpInvocationCorrelation | None = None


class McpToolInvocationLogEvent(Protocol):
    started: McpToolInvocationStarted
    duration_ms: float

    @property
    def outcome(self) -> McpToolInvocationOutcome: ...


@dataclass(frozen=True)
class McpToolInvocationSucceeded:
    started: McpToolInvocationStarted
    duration_ms: float

    @property
    def outcome(self) -> Literal[McpToolInvocationOutcome.SUCCESS]:
        return McpToolInvocationOutcome.SUCCESS


@dataclass(frozen=True)
class McpToolInvocationFailed:
    started: McpToolInvocationStarted
    duration_ms: float
    failure_category: McpToolInvocationFailureCategory

    @property
    def outcome(self) -> Literal[McpToolInvocationOutcome.FAILURE]:
        return McpToolInvocationOutcome.FAILURE


McpToolInvocationCompleted = McpToolInvocationSucceeded | McpToolInvocationFailed
