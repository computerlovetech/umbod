from __future__ import annotations

import asyncio
import hashlib
import json
import logging

import mcp.types as mt
import pytest

from fastmcp.exceptions import AuthorizationError, ValidationError
from fastmcp.server.middleware.middleware import MiddlewareContext
from fastmcp.tools import FunctionTool, ToolResult

from umbod.logging import create_application_failure_signal
from umbod.logging import OpenTelemetryJsonFormatter
from umbod.mcp.logging import (
    McpAuditActivityType,
    McpAuthenticatedAuditActor,
    McpAuditClientMetadata,
    McpAuditEvent,
    McpAuditFailureCategory,
    McpAuditIdentity,
    McpAuditOutcome,
    McpAuditRecorder,
)
from tests.support.signals import InMemorySignalFailureHandler
from umbod.mcp.listeners.invocation_audit import InvocationAuditReceiver
from umbod.core.invocation.diagnostics import NoInvocationFailureDiagnostic
from umbod.mcp.signals import (
    McpInvocationPublisher,
    McpSignals,
    McpToolIdentity,
    McpToolInvocationFailureCategory,
    McpInvocationActor,
    current_mcp_invocation_context,
)
from umbod.mcp.middleware import McpAuditMiddleware
from umbod.mcp.logging.audit.formatting import StructuredMcpAuditFormatter


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
        recorder=McpAuditRecorder(sink, "umbod", application_failures=create_application_failure_signal()),
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
    assert record.mcp_authenticated is True
    assert record.mcp_session_present is True


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
    assert record.mcp_authenticated is True
    assert record.mcp_session_present is True


class CanaryIdentitySource(FakeIdentitySource):
    def identity_from_request(self, fastmcp_context: object | None) -> McpAuditIdentity:
        return McpAuditIdentity(
            actor=McpAuthenticatedAuditActor("secret-canary-subject"),
            client=McpAuditClientMetadata({
                "client_id": "secret-canary-client-id",
                "client_name": "secret-canary-client-name",
                "session_id": "secret-canary-session",
                "request_id": "secret-canary-request",
            }),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["initialize", "tools/list"])
@pytest.mark.parametrize("exposure_mode", ["flat", "gateway", "codemode", "secret-canary-mode"])
async def test_debug_output_keeps_privacy_and_does_not_change_audit_identity(
    method: str, exposure_mode: str, caplog: pytest.LogCaptureFixture,
) -> None:
    sink = RecordingSink()
    middleware = McpAuditMiddleware(McpAuditRecorder(sink, "umbod", application_failures=create_application_failure_signal()), CanaryIdentitySource(), exposure_mode)

    async def private_tool() -> str:
        return "unused"

    request = mt.InitializeRequest(params=mt.InitializeRequestParams(
        protocolVersion="2025-06-18",
        capabilities=mt.ClientCapabilities(),
        clientInfo=mt.Implementation(name="secret-canary-client", version="secret-canary-version"),
    ))
    tools = [FunctionTool.from_function(private_tool, name="secret-canary-tool")]
    with caplog.at_level(logging.DEBUG, logger="umbod.mcp.middleware.audit"):
        if method == "initialize":
            await middleware.on_initialize(_context(method, request), CallNextStub("init", None))
        else:
            await middleware.on_list_tools(_context(method, object()), CallNextStub(tools, None))

    serialized = [OpenTelemetryJsonFormatter("test").format(record) for record in caplog.records]
    assert len(serialized) == 1
    assert "secret-canary" not in serialized[0]
    attributes = json.loads(serialized[0])["attributes"]
    expected: dict[str, object] = {
        "logger.name": "umbod.mcp.middleware.audit",
        "mcp_event": method,
        "mcp_exposure_mode": exposure_mode if exposure_mode in {"flat", "gateway", "codemode"} else "other",
        "mcp_authenticated": True,
        "mcp_session_present": True,
    }
    if method == "tools/list":
        expected["mcp_tool_count"] = 1
    assert attributes == expected
    assert sink.events[0].actor.authenticated_user_id == "secret-canary-subject"
    assert sink.events[0].client.attributes["client_id"] == "secret-canary-client-id"


@pytest.mark.asyncio
async def test_on_call_tool_success_restores_invocation_context_without_audit() -> None:
    sink = RecordingSink()
    message = mt.CallToolRequestParams(name="slack_post")

    previous = current_mcp_invocation_context()

    async def inspect_context(context: MiddlewareContext[object]) -> str:
        invocation = current_mcp_invocation_context()
        assert invocation is not None
        assert invocation.actor.authenticated_user_id == "user@example.com"
        assert invocation.server_name == "umbod"
        return "ok"

    result = await _middleware(sink).on_call_tool(
        _context("tools/call", message), inspect_context
    )

    assert result == "ok"
    assert sink.events == []
    assert current_mcp_invocation_context() is previous


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
    assert StructuredMcpAuditFormatter().format_mcp_activity(event).severity_text == (
        "INFO" if audit_outcome == McpAuditOutcome.SUCCESS else "WARNING"
    )
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


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["search_tools", "execute_tool", "execute_code"])
@pytest.mark.parametrize(("failure_type", "category", "severity"), [
    (RuntimeError, McpAuditFailureCategory.UNEXPECTED_ERROR, "ERROR"),
    (ValidationError, McpAuditFailureCategory.VALIDATION, "WARNING"),
])
async def test_fixed_tool_exception_is_audited_once_and_reraised(
    tool_name: str, failure_type: type[Exception], category: McpAuditFailureCategory, severity: str,
) -> None:
    sink = RecordingSink()
    code = "private code"
    message = mt.CallToolRequestParams(name=tool_name, arguments={"code": code})
    error = failure_type("private failure")

    with pytest.raises(failure_type) as raised:
        await _middleware(sink).on_call_tool(
            _context("tools/call", message), CallNextStub(None, error)
        )

    assert raised.value is error
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.outcome == McpAuditOutcome.FAILURE
    assert event.target.tool_name == tool_name
    assert event.failure_category == category
    assert StructuredMcpAuditFormatter().format_mcp_activity(event).severity_text == severity
    if tool_name == "execute_code":
        assert event.target.attributes["code_hash"] == hashlib.sha256(code.encode()).hexdigest()


@pytest.mark.asyncio
async def test_gateway_returned_error_is_audited_once_as_failure() -> None:
    sink = RecordingSink()
    message = mt.CallToolRequestParams(name="execute_tool")
    result = ToolResult(content=[], is_error=True)

    returned = await _middleware(sink).on_call_tool(
        _context("tools/call", message), CallNextStub(result, None)
    )

    assert returned is result
    assert len(sink.events) == 1
    assert sink.events[0].outcome == McpAuditOutcome.FAILURE
    assert sink.events[0].failure_category == McpAuditFailureCategory.TOOL_ERROR
    assert StructuredMcpAuditFormatter().format_mcp_activity(sink.events[0]).severity_text == "WARNING"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["execute_tool", "execute_code"])
@pytest.mark.parametrize("category", list(McpToolInvocationFailureCategory))
async def test_gateway_audit_preserves_nested_failure_classification_without_leaking_to_next_request(
    tool_name: str, category: McpToolInvocationFailureCategory,
) -> None:
    sink = RecordingSink()
    recorder = McpAuditRecorder(sink, "umbod", application_failures=create_application_failure_signal())
    signals = McpSignals(InMemorySignalFailureHandler())
    signals.invocation_completed.connect("audit", InvocationAuditReceiver(recorder))
    publisher = McpInvocationPublisher(signals)
    message = mt.CallToolRequestParams(name=tool_name)
    result = ToolResult(content=[], is_error=True)

    async def nested_failure(context: MiddlewareContext[object]) -> ToolResult:
        lifecycle = publisher.start(McpToolIdentity("nested_tool", "connector", "operation"))
        publisher.failed(lifecycle, category, NoInvocationFailureDiagnostic(), None)
        return result

    middleware = _middleware(sink)
    returned = await middleware.on_call_tool(_context("tools/call", message), nested_failure)

    assert returned is result
    assert len(sink.events) == 2
    assert sink.events[-1].failure_category.value == category.value
    expected_severity = "ERROR" if category in {
        McpToolInvocationFailureCategory.CONNECTOR_ERROR, McpToolInvocationFailureCategory.UNEXPECTED_ERROR,
    } else "WARNING"
    assert StructuredMcpAuditFormatter().format_mcp_activity(sink.events[-1]).severity_text == expected_severity

    await middleware.on_call_tool(_context("tools/call", message), CallNextStub(result, None))

    assert len(sink.events) == 3
    assert sink.events[-1].failure_category == McpAuditFailureCategory.TOOL_ERROR
    assert StructuredMcpAuditFormatter().format_mcp_activity(sink.events[-1]).severity_text == "WARNING"


@pytest.mark.asyncio
async def test_fixed_tool_cancellation_is_not_audited() -> None:
    sink = RecordingSink()
    message = mt.CallToolRequestParams(name="execute_code")

    async def cancelled(context: MiddlewareContext[object]) -> ToolResult:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await _middleware(sink).on_call_tool(_context("tools/call", message), cancelled)

    assert sink.events == []
