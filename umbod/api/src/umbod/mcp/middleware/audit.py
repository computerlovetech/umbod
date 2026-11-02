from __future__ import annotations

import hashlib
import logging
import time
import uuid

from collections.abc import Sequence

import mcp.types as mt

from fastmcp.exceptions import AuthorizationError
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import Tool, ToolResult

from umbod.http_metadata import current_request_id
from umbod.mcp.logging import (
    McpAuditCorrelation,
    McpAuditIdentitySource,
)
from umbod.mcp.signals import (
    McpInvocationContext,
    McpInvocationCorrelation,
    McpToolIdentity,
    set_mcp_invocation_context,
    reset_mcp_invocation_context,
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
        self._exposure_mode = exposure_mode if exposure_mode in {"flat", "gateway", "codemode"} else "other"

    async def on_initialize(
        self,
        context: MiddlewareContext[mt.InitializeRequest],
        call_next: CallNext[mt.InitializeRequest, mt.InitializeResult | None],
    ) -> mt.InitializeResult | None:
        result = await call_next(context)
        identity = self._identity_source.identity_from_request(context.fastmcp_context)
        self._recorder.record_client_connection(identity, _new_correlation())
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "MCP client initialized",
                extra={
                    "mcp_event": "initialize",
                    "mcp_exposure_mode": self._exposure_mode,
                    "mcp_authenticated": identity.actor.authenticated_user_id is not None,
                    "mcp_session_present": "session_id" in identity.client.attributes,
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
            logger.debug(
                "MCP tools listed",
                extra={
                    "mcp_event": "tools/list",
                    "mcp_exposure_mode": self._exposure_mode,
                    "mcp_authenticated": identity.actor.authenticated_user_id is not None,
                    "mcp_tool_count": len(result),
                    "mcp_session_present": "session_id" in identity.client.attributes,
                },
            )
        return result

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        correlation = _new_correlation()
        token = set_mcp_invocation_context(
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
                audit_result = (
                    McpAuditFailure(McpAuditFailureCategory.UNEXPECTED_ERROR)
                    if result.is_error else McpAuditSuccess()
                )
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
        except Exception:
            if context.message.name in {"search_tools", "execute_tool", "execute_code"}:
                target = (
                    self._recorder.code_execution_target(_code_hash(context.message))
                    if context.message.name == "execute_code"
                    else self._recorder.tool_target(_tool_identity(context.message))
                )
                self._recorder.record_tool_invocation(
                    self._identity_source.identity_from_request(context.fastmcp_context),
                    target,
                    McpAuditFailure(McpAuditFailureCategory.UNEXPECTED_ERROR),
                    correlation,
                    time.time_ns(),
                )
            raise
        finally:
            reset_mcp_invocation_context(token)


def _new_correlation() -> McpAuditCorrelation:
    return McpAuditCorrelation(trace_id=current_request_id() or uuid.uuid4().hex, span_id=None)


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
