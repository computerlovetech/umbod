from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class ApplicationFailureKind(Enum):
    USAGE_PROJECTION = ('MCP usage projection dropped', 'mcp_usage', 'project', 'projection_failed')
    USAGE_OVERSIZED = ('MCP usage record dropped', 'mcp_usage', 'enqueue', 'oversized')
    USAGE_OVERFLOW = ('MCP usage queue full', 'mcp_usage', 'enqueue', 'overflow')
    USAGE_WRITE = ('MCP usage batch dropped', 'mcp_usage', 'append', 'retries_exhausted')
    USAGE_SHUTDOWN = ('MCP usage shutdown loss', 'mcp_usage', 'shutdown', 'shutdown_loss')
    USAGE_RETENTION = ('MCP usage retention failed', 'mcp_usage', 'prune', 'prune_failed')
    REST_METRICS = ("REST metrics recording failed", "rest_metrics", "record_request", "recorder_failed")
    CONNECTOR_LOOKUP = (
        "OpenAPI connector display name lookup failed", "openapi_codemode",
        "lookup_display_name", "lookup_failed",
    )
    SIGNAL_RECEIVER = ("Signal receiver failed", "signals", "deliver_signal", "receiver_failed")
    AUDIT_SINK = ("MCP audit logging failed", "mcp_audit", "record_activity", "sink_failed")


@dataclass(frozen=True)
class NoFailureContext:
    pass


@dataclass(frozen=True)
class RestFailureContext:
    method: str
    status_code: int
    normalized_route: str


@dataclass(frozen=True)
class CorrelatedFailureContext:
    trace_id: str
    span_id: str | None


@dataclass(frozen=True)
class ConnectorLookupFailureContext:
    connector_id: str
    operation_name: str


@dataclass(frozen=True)
class SignalFailureContext:
    receiver_name: str


FailureContext: TypeAlias = (
    NoFailureContext | RestFailureContext | CorrelatedFailureContext
    | ConnectorLookupFailureContext | SignalFailureContext
)
FailureAttribute: TypeAlias = Literal[
    "event.name", "component", "operation", "reason", "outcome", "failure.origin",
    "exception.type", "exception.stacktrace", "method", "status_code",
    "normalized_route", "connector.id_hash", "operation.name_hash",
    "receiver.name", "receiver.name_hash",
]


class ApplicationFailure(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: ApplicationFailureKind
    attributes: tuple[tuple[FailureAttribute, Annotated[str, Field(max_length=4096)] | int], ...] = Field(max_length=18)
    correlation: CorrelatedFailureContext | NoFailureContext
