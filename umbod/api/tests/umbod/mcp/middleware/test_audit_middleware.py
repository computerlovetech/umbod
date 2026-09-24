from __future__ import annotations

import logging

import mcp.types as mt
import pytest

from fastmcp.exceptions import AuthorizationError
from fastmcp.server.middleware.middleware import MiddlewareContext
from fastmcp.tools import FunctionTool, ToolResult

from umbod.mcp.logging import (
    McpAuditActivityType,
    McpAuthenticatedAuditActor,
    McpAuditClientMetadata,
    McpAuditEvent,
    McpAuditFailureCategory,
    McpAuditIdentity,
    McpAuditOutcome,
    McpAuditRecorder,
    McpInvocationActor,
    current_mcp_invocation_context,
)
from umbod.mcp.middleware import McpAuditMiddleware


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[McpAuditEvent] = []

    def record_mcp_activity(self, event: McpAuditEvent) -> None:
        self.events.append(event)


class FakeIdentitySource:
    def __init__(self) -> None:
        self._identity = McpAuditIdentity(
            actor=McpAuthenticatedAuditActor("user@example.com"),
            client=McpAuditClientMetadata(
                {
                    "client_id": "oauth-client-id",
                    "client_name": "oauth-client-name",
                    "session_id": "session-1",
                }
            ),
        )
        self._invocation_actor = McpInvocationActor(
            authenticated_user_id="user@example.com",
            agent_client_id="claude-code",
            session_id="session-1",
        )

    def identity_from_request(self, fastmcp_context: object | None) -> McpAuditIdentity:
        return self._identity

    def invocation_actor(self, fastmcp_context: object | None) -> McpInvocationActor:
        return self._invocation_actor


class CallNextStub:
    def __init__(self, result: object, error: Exception | None) -> None:
        self._result = result
        self._error = error

    async def __call__(self, context: MiddlewareContext[object]) -> object:
        if self._error is not None:
            raise self._error
        return self._result


def _middleware(sink: RecordingSink) -> McpAuditMiddleware:
    return McpAuditMiddleware(
        recorder=McpAuditRecorder(sink, "umbod"),
        identity_source=FakeIdentitySource(),
        exposure_mode="flat",
    )


def _context(method: str, message: object) -> MiddlewareContext[object]:
    return MiddlewareContext(message=message, method=method)


@pytest.mark.asyncio
async def test_on_initialize_records_client_connection(caplog: pytest.LogCaptureFixture) -> None:
    sink = RecordingSink()
    request = mt.InitializeRequest(
        params=mt.InitializeRequestParams(
            protocolVersion="2025-06-18",
            capabilities=mt.ClientCapabilities(),
            clientInfo=mt.Implementation(name="claude-ai", version="1.0"),
        )
    )

    with caplog.at_level(logging.DEBUG):
        result = await _middleware(sink).on_initialize(
            _context("initialize", request), CallNextStub("init", None)
        )

    assert result == "init"
    assert sink.events[0].activity_type == McpAuditActivityType.CLIENT_CONNECTION
    assert sink.events[0].outcome == McpAuditOutcome.SUCCESS
    assert sink.events[0].actor.authenticated_user_id == "user@example.com"
    record = next(record for record in caplog.records if record.msg == "MCP client initialized")
    assert record.mcp_exposure_mode == "flat"
    assert record.mcp_client_name == "claude-ai"
    assert record.mcp_client_version == "1.0"
    assert record.mcp_oauth_client_id == "oauth-client-id"
    assert record.mcp_oauth_client_name == "oauth-client-name"
    assert record.mcp_authenticated_subject == "user@example.com"
    assert record.mcp_session_id == "session-1"


@pytest.mark.asyncio
async def test_on_list_tools_records_tool_discovery(caplog: pytest.LogCaptureFixture) -> None:
    sink = RecordingSink()

    async def search_tools() -> str:
        return "found"

    tools = [FunctionTool.from_function(search_tools, name="search_tools")]
    with caplog.at_level(logging.DEBUG):
        result = await _middleware(sink).on_list_tools(
            _context("tools/list", object()), CallNextStub(tools, None)
        )

    assert result == tools
    assert sink.events[0].activity_type == McpAuditActivityType.TOOL_DISCOVERY
    assert sink.events[0].outcome == McpAuditOutcome.SUCCESS
    record = next(record for record in caplog.records if record.msg == "MCP tools listed")
    assert record.mcp_exposure_mode == "flat"
    assert record.mcp_tool_count == 1
    assert record.mcp_tool_names == ["search_tools"]
    assert record.mcp_tool_names_hash == (
        "29693a83b3796e3fcfa0d4806d2730ebd1a9c5ceba33da071431355fcc25aaf3"
    )
    assert record.mcp_authenticated_subject == "user@example.com"
    assert record.mcp_session_id == "session-1"


@pytest.mark.asyncio
async def test_on_call_tool_success_sets_invocation_context_without_audit() -> None:
    sink = RecordingSink()
    message = mt.CallToolRequestParams(name="slack_post")

    result = await _middleware(sink).on_call_tool(
        _context("tools/call", message), CallNextStub("ok", None)
    )

    assert result == "ok"
    assert sink.events == []
    context = current_mcp_invocation_context()
    assert context is not None
    assert context.actor.authenticated_user_id == "user@example.com"
    assert context.server_name == "umbod"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "audit_outcome"),
    [
        ("success", McpAuditOutcome.SUCCESS),
        ("failure", McpAuditOutcome.FAILURE),
        ("timeout", McpAuditOutcome.FAILURE),
    ],
)
async def test_on_execute_code_records_hash_and_outcome(
    outcome: str, audit_outcome: McpAuditOutcome
) -> None:
    sink = RecordingSink()
    code = "print('private')"
    message = mt.CallToolRequestParams(name="execute_code", arguments={"code": code})
    result = ToolResult(structured_content={"outcome": outcome})

    await _middleware(sink).on_call_tool(
        _context("tools/call", message), CallNextStub(result, None)
    )

    event = sink.events[0]
    assert event.outcome == audit_outcome
    assert event.target.tool_name == "execute_code"
    assert (
        event.target.attributes["code_hash"]
        == "7e632a026569c75ff1636ef9e3a5cbc6400994c282648420925f1795054dcace"
    )
    assert code not in event.target.attributes.values()


@pytest.mark.asyncio
async def test_on_call_tool_denied_records_denied_and_reraises() -> None:
    sink = RecordingSink()
    message = mt.CallToolRequestParams(name="slack_post")
    call_next = CallNextStub(None, AuthorizationError("insufficient permissions"))

    with pytest.raises(AuthorizationError):
        await _middleware(sink).on_call_tool(_context("tools/call", message), call_next)

    event = sink.events[0]
    assert event.activity_type == McpAuditActivityType.TOOL_INVOCATION
    assert event.outcome == McpAuditOutcome.DENIED
    assert event.failure_category == McpAuditFailureCategory.AUTHORIZATION
    assert event.target.tool_name == "slack_post"
