from __future__ import annotations

import logging
import time

from umbod.mcp.logging.audit.event import (
    McpAuditActivityType,
    McpAuditCorrelation,
    McpAuditDenied,
    McpAuditEvent,
    McpAuditEventSink,
    McpAuditFailure,
    McpAuditFailureCategory,
    McpAuditResult,
    McpAuditSuccess,
    McpAuditTargetState,
    McpServerAuditTarget,
    McpToolAuditTarget,
)
from umbod.mcp.logging.audit.identity import McpAuditIdentity
from umbod.mcp.logging.audit.sink import create_default_mcp_audit_event_sink
from umbod.mcp.logging.invocation.event import McpToolIdentity

logger = logging.getLogger(__name__)


class McpAuditRecorder:
    def __init__(self, sink: McpAuditEventSink, server_name: str) -> None:
        self._sink = sink
        self._server_name = server_name

    @property
    def server_name(self) -> str:
        return self._server_name

    def tool_target(self, tool: McpToolIdentity) -> McpAuditTargetState:
        return McpToolAuditTarget(
            server_name=self._server_name,
            tool_name=tool.tool_name,
            attributes=_present_metadata(
                connector_id=tool.connector_id,
                connector_name=tool.connector_name or tool.connector_id,
                operation_name=tool.operation_name,
            ),
        )

    def record_client_connection(
        self, identity: McpAuditIdentity, correlation: McpAuditCorrelation
    ) -> None:
        self._record(
            McpAuditActivityType.CLIENT_CONNECTION,
            identity,
            self._server_target(),
            McpAuditSuccess(),
            correlation,
            time.time_ns(),
        )

    def record_tool_discovery(
        self, identity: McpAuditIdentity, correlation: McpAuditCorrelation
    ) -> None:
        self._record(
            McpAuditActivityType.TOOL_DISCOVERY,
            identity,
            self._server_target(),
            McpAuditSuccess(),
            correlation,
            time.time_ns(),
        )

    def code_execution_target(self, code_hash: str) -> McpAuditTargetState:
        return McpToolAuditTarget(
            server_name=self._server_name,
            tool_name="execute_code",
            attributes={"code_hash": code_hash},
        )

    def record_tool_invocation_denied(
        self,
        identity: McpAuditIdentity,
        target: McpAuditTargetState,
        correlation: McpAuditCorrelation,
    ) -> None:
        self._record(
            McpAuditActivityType.TOOL_INVOCATION,
            identity,
            target,
            McpAuditDenied(McpAuditFailureCategory.AUTHORIZATION),
            correlation,
            time.time_ns(),
        )

    def record_tool_invocation(
        self,
        identity: McpAuditIdentity,
        target: McpAuditTargetState,
        result: McpAuditSuccess | McpAuditFailure,
        correlation: McpAuditCorrelation,
        occurred_at_unix_nano: int,
    ) -> None:
        self._record(
            McpAuditActivityType.TOOL_INVOCATION,
            identity,
            target,
            result,
            correlation,
            occurred_at_unix_nano,
        )

    def _server_target(self) -> McpAuditTargetState:
        return McpServerAuditTarget(server_name=self._server_name)

    def _record(
        self,
        activity_type: McpAuditActivityType,
        identity: McpAuditIdentity,
        target: McpAuditTargetState,
        result: McpAuditResult,
        correlation: McpAuditCorrelation,
        occurred_at_unix_nano: int,
    ) -> None:
        try:
            self._sink.record_mcp_activity(
                McpAuditEvent(
                    activity_type=activity_type,
                    actor=identity.actor,
                    client=identity.client,
                    target=target,
                    result=result,
                    occurred_at_unix_nano=occurred_at_unix_nano,
                    correlation=correlation,
                )
            )
        except Exception:
            logger.error("MCP audit logging failed")


def _present_metadata(**values: str | None) -> dict[str, str]:
    return {key: value for key, value in values.items() if value is not None}


def create_default_mcp_audit_recorder(server_name: str) -> McpAuditRecorder:
    return McpAuditRecorder(create_default_mcp_audit_event_sink(), server_name)
