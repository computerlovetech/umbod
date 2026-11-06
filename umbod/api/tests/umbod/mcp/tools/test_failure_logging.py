import json
from io import StringIO
from typing import Any
from unittest.mock import Mock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from tests.support.signals import InMemorySignalFailureHandler
from umbod.core.invocation.failure_evidence import InvocationExceptionEvidence, InvocationFailureOrigin
from umbod.core.responses import RetryAdvice, ToolErrorDetails
from umbod.logging import create_application_failure_signal
from umbod.mcp.filesystem.argument_errors import FilesystemArgumentErrorsTool
from umbod.mcp.filesystem.browsing import FilesystemBrowseTool
from umbod.mcp.listeners.invocation_audit import InvocationAuditReceiver
from umbod.mcp.logging.audit.formatting import StructuredMcpAuditFormatter
from umbod.mcp.logging.audit.recorder import McpAuditRecorder
from umbod.mcp.logging.audit.sink import StdoutMcpAuditEventSink
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import StdoutMcpToolInvocationLogSink
from umbod.mcp.signals import McpInvocationPublisher, McpSignals, McpToolInvocationCompleted, McpToolInvocationFailed
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.tools.errors import BuiltinToolApprovalDenied, BuiltinToolAuthorizationDenied, BuiltinToolError, BuiltinToolRejected


def _logging_publisher(output: StringIO, events: list[McpToolInvocationCompleted]) -> McpInvocationPublisher:
    signals = McpSignals(InMemorySignalFailureHandler())
    invocation_sink = StdoutMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter(), output)
    audit_sink = StdoutMcpAuditEventSink(StructuredMcpAuditFormatter(), output)
    recorder = McpAuditRecorder(audit_sink, "test", application_failures=create_application_failure_signal())
    signals.invocation_completed.connect("capture", events.append)
    signals.invocation_completed.connect("logging", invocation_sink.record_invocation_completed)
    signals.invocation_completed.connect("audit", InvocationAuditReceiver(recorder))
    return McpInvocationPublisher(signals)


def _records(output: StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in output.getvalue().splitlines()]


@pytest.mark.asyncio
async def test_invalid_browse_arguments_return_corrections_and_warn_in_both_streams() -> None:
    output = StringIO()
    events: list[McpToolInvocationCompleted] = []
    callers = Mock()
    services = Mock()
    delegate = FilesystemArgumentErrorsTool(FilesystemBrowseTool(callers, services))
    tool = McpObservedToolRegistrar(FastMCP("test"), _logging_publisher(output, events)).register_tool(
        delegate, result_is_error=lambda result: result.is_error,
        operation_names=frozenset({"tree"}), builtin_response=True,
    )

    result = await tool.run({"operation": "tree", "target": {"type": "path", "path": "private-relative-path-sentinel"}})

    assert result.is_error is True
    assert "Use an absolute path" in result.content[0].text
    assert result.meta["computerlove.tech/umbod"]["guidance"]["recovery"]["retry"] == "after_correction"
    callers.capture.assert_not_called()
    services.browsing.assert_not_called()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, McpToolInvocationFailed)
    assert event.evidence.origin == InvocationFailureOrigin.CLIENT_INPUT
    assert not isinstance(event.evidence, InvocationExceptionEvidence)
    records = _records(output)
    assert len(records) == 2
    assert {record["body"] for record in records} == {"mcp tool invocation completed", "mcp audit event"}
    assert {record["severity_text"] for record in records} == {"WARNING"}
    assert {record["attributes"]["mcp.failure.category"] for record in records} == {"validation"}
    assert len({record["trace_id"] for record in records}) == 1
    assert all("exception.stacktrace" not in record["attributes"] for record in records)
    assert "private-relative-path-sentinel" not in output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_type", "category", "severity"),
    [
        (BuiltinToolRejected, "tool_error", "WARNING"),
        (BuiltinToolAuthorizationDenied, "authorization", "WARNING"),
        (BuiltinToolApprovalDenied, "authorization", "WARNING"),
        (BuiltinToolError, "unexpected_error", "ERROR"),
        (ToolError, "unexpected_error", "ERROR"),
        (RuntimeError, "unexpected_error", "ERROR"),
    ],
)
async def test_expected_rejections_warn_but_backend_exceptions_remain_errors_in_both_streams(
    failure_type: type[Exception], category: str, severity: str,
) -> None:
    output = StringIO()
    events: list[McpToolInvocationCompleted] = []
    details = ToolErrorDetails(code="test_failure", message="Safe failure.", issues=())
    if issubclass(failure_type, BuiltinToolError):
        failure = failure_type("private-exception-sentinel", details=details, retry=RetryAdvice.AFTER_CORRECTION)
    elif issubclass(failure_type, BuiltinToolAuthorizationDenied):
        failure = failure_type("private-exception-sentinel", details=details)
    else:
        failure = failure_type("private-exception-sentinel")

    async def invoke() -> None:
        raise failure

    tool = McpObservedToolRegistrar(FastMCP("test"), _logging_publisher(output, events)).register(
        invoke, name="test_tool", description="Test tool", auth=None, builtin_response=True,
    )

    result = await tool.run({})

    assert result.is_error is True
    assert len(events) == 1
    records = _records(output)
    assert len(records) == 2
    assert {record["severity_text"] for record in records} == {severity}
    assert {record["attributes"]["mcp.failure.category"] for record in records} == {category}
    invocation = next(record for record in records if record["body"] == "mcp tool invocation completed")
    assert ("exception.stacktrace" in invocation["attributes"]) == (severity == "ERROR")
    assert "private-exception-sentinel" not in output.getvalue()
