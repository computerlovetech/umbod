from __future__ import annotations

import hashlib
import logging
import time
import uuid

from collections.abc import Mapping, Sequence

import mcp.types as mt

from fastmcp.exceptions import AuthorizationError
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import Tool, ToolResult

from umbod.mcp.logging import (
    McpAuditCorrelation,
    McpAuditIdentitySource,
    McpInvocationContext,
    McpInvocationCorrelation,
    McpToolIdentity,
    set_mcp_invocation_context,
)
from umbod.mcp.logging.audit.event import (
    McpAuditFailure,
    McpAuditFailureCategory,
    McpAuditSuccess,
)
from umbod.mcp.logging.audit.recorder import McpAuditRecorder


logger = logging.getLogger(__name__)


class McpAuditMiddleware(Middleware):
    def __init__(
        self,
        recorder: McpAuditRecorder,
        identity_source: McpAuditIdentitySource,
        exposure_mode: str,
    ) -> None:
        self._recorder = recorder
        self._identity_source = identity_source
        self._exposure_mode = exposure_mode

    async def on_initialize(
        self,
        context: MiddlewareContext[mt.InitializeRequest],
        call_next: CallNext[mt.InitializeRequest, mt.InitializeResult | None],
    ) -> mt.InitializeResult | None:
        result = await call_next(context)
        identity = self._identity_source.identity_from_request(context.fastmcp_context)
        self._recorder.record_client_connection(identity, _new_correlation())
        if logger.isEnabledFor(logging.DEBUG):
            client_info = context.message.params.client_info
            logger.debug(
                "MCP client initialized",
                extra={
                    "mcp_event": "initialize",
                    "mcp_exposure_mode": self._exposure_mode,
                    "mcp_client_name": client_info.name,
                    "mcp_client_version": client_info.version,
                    "mcp_authenticated_subject": identity.actor.authenticated_user_id,
                    **_client_metadata(identity.client.attributes),
                },
            )
        return result

    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        result = await call_next(context)
        identity = self._identity_source.identity_from_request(context.fastmcp_context)
        self._recorder.record_tool_discovery(identity, _new_correlation())
        if logger.isEnabledFor(logging.DEBUG):
            tool_names = sorted(tool.name for tool in result)
            logger.debug(
                "MCP tools listed",
                extra={
                    "mcp_event": "tools/list",
                    "mcp_exposure_mode": self._exposure_mode,
                    "mcp_authenticated_subject": identity.actor.authenticated_user_id,
                    "mcp_tool_count": len(tool_names),
                    "mcp_tool_names": tool_names,
                    "mcp_tool_names_hash": _tool_names_hash(tool_names),
                    **_client_metadata(identity.client.attributes),
                },
            )
        return result

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        correlation = _new_correlation()
        set_mcp_invocation_context(
            McpInvocationContext(
                actor=self._identity_source.invocation_actor(context.fastmcp_context),
                correlation=McpInvocationCorrelation(
                    trace_id=correlation.trace_id, span_id=correlation.span_id
                ),
                server_name=self._recorder.server_name,
            )
        )
        try:
            result = await call_next(context)
            if context.message.name in {"search_tools", "execute_tool", "execute_code"}:
                target = self._recorder.tool_target(_tool_identity(context.message))
                audit_result = McpAuditSuccess()
                if context.message.name == "execute_code":
                    target = self._recorder.code_execution_target(_code_hash(context.message))
                    if _code_execution_failed(result):
                        audit_result = McpAuditFailure(McpAuditFailureCategory.UNEXPECTED_ERROR)
                self._recorder.record_tool_invocation(
                    self._identity_source.identity_from_request(context.fastmcp_context),
                    target,
                    audit_result,
                    correlation,
                    time.time_ns(),
                )
            return result
        except AuthorizationError:
            self._recorder.record_tool_invocation_denied(
                self._identity_source.identity_from_request(context.fastmcp_context),
                self._recorder.tool_target(_tool_identity(context.message)),
                correlation,
            )
            raise


def _client_metadata(attributes: Mapping[str, str]) -> dict[str, str]:
    field_names = {
        "client_id": "mcp_oauth_client_id",
        "client_name": "mcp_oauth_client_name",
        "session_id": "mcp_session_id",
        "request_id": "mcp_request_id",
    }
    return {
        field_names[key]: value
        for key, value in attributes.items()
        if key in field_names and isinstance(value, str)
    }


def _tool_names_hash(tool_names: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(tool_names).encode("utf-8")).hexdigest()


def _new_correlation() -> McpAuditCorrelation:
    return McpAuditCorrelation(trace_id=uuid.uuid4().hex, span_id=None)


def _tool_identity(message: mt.CallToolRequestParams) -> McpToolIdentity:
    return McpToolIdentity(tool_name=message.name, connector_id=None, operation_name=None)


def _code_hash(message: mt.CallToolRequestParams) -> str:
    arguments = message.arguments or {}
    code = arguments.get("code", "")
    encoded_code = code.encode("utf-8") if isinstance(code, str) else b""
    return hashlib.sha256(encoded_code).hexdigest()


def _code_execution_failed(result: ToolResult) -> bool:
    structured_content = result.structured_content or {}
    return structured_content.get("outcome") != "success"
