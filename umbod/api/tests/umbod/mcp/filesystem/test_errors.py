import asyncio
import json
from dataclasses import dataclass
from io import StringIO
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from umbod.logging import create_application_failure_signal
from umbod.core.filesystem.authorization.errors import PermissionDenied
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.creation import FilesystemCreation
from umbod.core.filesystem.deletion import FilesystemDeletion
from umbod.core.filesystem.sharing import InvalidSharingPolicy, SharingPolicyUnavailable
from umbod.core.filesystem.content.errors import UploadTooLarge
from umbod.core.filesystem.uploads.errors import (
    UploadConflict, UploadExpired, UploadLengthMismatch, UploadMediaTypeMismatch,
)
from umbod.core.filesystem.errors import InvalidName, MissingNode, NameCollision, RevisionConflict, StorageFailure, WrongNodeKind
from umbod.mcp.filesystem import register_filesystem_tools
from umbod.mcp.filesystem.errors import filesystem_operation
from umbod.mcp.filesystem.ports import FilesystemCallerCapture, FilesystemDeletionApproval, FilesystemServiceFactory
from umbod.mcp.filesystem.authorization import FilesystemToolVisibility
from umbod.mcp.metrics.in_memory import InMemoryMcpMetricsRecorder
from umbod.core.callers import AuthenticationProvenance
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.logging.audit.formatting import StructuredMcpAuditFormatter
from umbod.mcp.logging.audit.recorder import McpAuditRecorder
from umbod.mcp.logging.audit.sink import StdoutMcpAuditEventSink
from umbod.mcp.logging.invocation.formatting import StructuredMcpToolInvocationLogFormatter
from umbod.mcp.logging.invocation.sink import StdoutMcpToolInvocationLogSink
from umbod.mcp.signals import (
    McpInvocationActor, McpInvocationContext, McpInvocationCorrelation,
    McpInvocationPublisher, set_mcp_invocation_context,
)
from .conftest import ScopedCallerCapture, caller_snapshot


@dataclass
class FilesystemErrorContext:
    callers: ScopedCallerCapture
    metrics: InMemoryMcpMetricsRecorder
    visibility: FilesystemToolVisibility
    approval: FilesystemDeletionApproval


@pytest.fixture
def filesystem_error_context() -> FilesystemErrorContext:
    callers = ScopedCallerCapture()
    callers.current.set(caller_snapshot(
        "alice", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
    ))
    visibility = Mock(spec=FilesystemToolVisibility)
    visibility.authorize = AsyncMock(return_value=True)
    return FilesystemErrorContext(
        callers, InMemoryMcpMetricsRecorder(), visibility, Mock(spec=FilesystemDeletionApproval),
    )


class SpecializedStorageFailure(StorageFailure):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type,expected", [
    (InvalidSharingPolicy, "filesystem_invalid_sharing_policy: Invalid filesystem sharing policy. Select valid recipients and permissions, then retry."),
    (SharingPolicyUnavailable, "filesystem_policy_unavailable: Filesystem sharing configuration unavailable. Ask an administrator to check the sharing configuration."),
    (UploadTooLarge, "filesystem_upload_too_large: Filesystem upload too large. Use filesystem_begin_upload for files above the 10 MiB inline limit; the configured server limit still applies."),
    (UploadConflict, "filesystem_upload_conflict: Filesystem upload conflict."),
    (UploadExpired, "filesystem_upload_expired: Filesystem upload expired."),
    (UploadLengthMismatch, "filesystem_upload_length_mismatch: Invalid upload length."),
    (UploadMediaTypeMismatch, "filesystem_upload_media_type_mismatch: Invalid upload content type. Send the Content-Type specified by the upload transfer instructions."),
    (PermissionDenied, "filesystem_permission_denied: Filesystem access denied. Choose an accessible node or ask its owner for the required permissions."),
    (MissingNode, "filesystem_permission_denied: Filesystem access denied. Choose an accessible node or ask its owner for the required permissions."),
    (InvalidName, "filesystem_invalid_name: Invalid filesystem name. Use a nonempty UTF-8 name other than . or .., without slashes, backslashes, or null characters."),
    (NameCollision, "filesystem_name_collision: Filesystem name already exists. Inspect the existing node before retrying, or choose a different name."),
    (RevisionConflict, "filesystem_revision_conflict: Filesystem revision conflict. Read the current node, review its changes, and retry with its current revision."),
    (WrongNodeKind, "filesystem_wrong_node_kind: Invalid filesystem node kind. Inspect the node and select the file or directory required by this operation."),
    (StorageFailure, "filesystem_storage_failure: Filesystem storage unavailable."),
    (SpecializedStorageFailure, "filesystem_storage_failure: Filesystem storage unavailable."),
])
async def test_expected_domain_failures_do_not_leak_details(
    filesystem_error_context: FilesystemErrorContext, error_type: type[Exception], expected: str,
) -> None:
    application_failures = create_application_failure_signal()
    server = FastMCP()
    browsing = Mock(spec=FilesystemBrowsing)
    browsing.get_root = AsyncMock(side_effect=error_type("SECRET backend /private/path"))
    factory = Mock(spec=FilesystemServiceFactory)
    factory.browsing.return_value = browsing
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(create_mcp_signals(Mock(), filesystem_error_context.metrics, Mock(), application_failures=application_failures))),
        filesystem_error_context.callers, factory, filesystem_error_context.visibility, filesystem_error_context.approval,
    )
    async with Client(server) as client:
        result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == expected
    assert "SECRET" not in repr(result)
    assert "/private/path" not in repr(result)
    guidance = result.meta["computerlove.tech/umbod"]["guidance"]
    assert guidance["recovery"]["instructions"]
    for instruction in guidance["recovery"]["instructions"]:
        assert instruction in result.content[1].text
    assert any(sample.labels["outcome"] == "failure" for sample in filesystem_error_context.metrics.metric_samples())


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type,category,severity", [
    (PermissionDenied, "authorization", 13),
    (MissingNode, "authorization", 13),
    (StorageFailure, "unexpected_error", 17),
    (RuntimeError, "unexpected_error", 17),
    (ToolError, "unexpected_error", 17),
])
async def test_filesystem_failures_emit_classified_invocation_and_audit_records(
    filesystem_error_context: FilesystemErrorContext, error_type: type[Exception],
    category: str, severity: int,
) -> None:
    application_failures = create_application_failure_signal()
    output = StringIO()
    server = FastMCP()
    browsing = Mock(spec=FilesystemBrowsing)
    browsing.get_root = AsyncMock(side_effect=error_type("SECRET backend /private/path"))
    factory = Mock(spec=FilesystemServiceFactory)
    factory.browsing.return_value = browsing
    signals = create_mcp_signals(
        StdoutMcpToolInvocationLogSink(StructuredMcpToolInvocationLogFormatter(), output),
        filesystem_error_context.metrics,
        McpAuditRecorder(StdoutMcpAuditEventSink(StructuredMcpAuditFormatter(), output), "test", application_failures=application_failures),
     application_failures=application_failures)
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(signals)),
        filesystem_error_context.callers, factory, filesystem_error_context.visibility, filesystem_error_context.approval,
    )
    set_mcp_invocation_context(McpInvocationContext(
        actor=McpInvocationActor(authenticated_user_id="test-caller"),
        correlation=McpInvocationCorrelation(trace_id="test-trace", span_id="test-span"),
        server_name="test",
    ))

    async with Client(server) as client:
        result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)

    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert result.is_error
    assert len(records) == 2
    assert {record["body"] for record in records} == {"mcp tool invocation completed", "mcp audit event"}
    for record in records:
        assert record["attributes"]["mcp.failure.category"] == category
        assert record["attributes"]["mcp.tool.name"] == "get_filesystem_root"
        assert record["attributes"]["enduser.id"] == "test-caller"
        assert record["trace_id"] == "test-trace"
        assert record["severity_number"] == severity
    invocation = next(record for record in records if record["body"] == "mcp tool invocation completed")
    if category == "authorization":
        assert result.content[0].text == "filesystem_permission_denied: Filesystem access denied. Choose an accessible node or ask its owner for the required permissions."
        assert invocation["attributes"]["mcp.failure.origin"] == "client_input"
        assert "exception.type" not in invocation["attributes"]
        assert "exception.stacktrace" not in invocation["attributes"]
    else:
        assert invocation["attributes"]["mcp.failure.origin"] == "internal"
        assert "exception.stacktrace" in invocation["attributes"]
    assert "SECRET" not in output.getvalue()
    assert "/private/path" not in output.getvalue()
    assert any(sample.labels["outcome"] == "failure" for sample in filesystem_error_context.metrics.metric_samples())


TOOL_OPERATIONS = [
    ("filesystem_delete_file", "check_delete_eligibility", {
        "node_id": "00000000-0000-0000-0000-000000000001", "expected_revision": 1,
    }),
    ("get_filesystem_root", "get_root", {}),
    ("get_filesystem_node", "get_node", {"node_id": "00000000-0000-0000-0000-000000000001"}),
    ("list_filesystem_children", "list_children", {"parent_id": "00000000-0000-0000-0000-000000000001"}),
    ("create_filesystem_file", "create_file", {
        "parent_id": "00000000-0000-0000-0000-000000000001", "name": "empty",
        "metadata": {"content_type": {}, "attributes": {}},
    }),
    ("create_filesystem_directory", "create_directory", {
        "parent_id": "00000000-0000-0000-0000-000000000001", "name": "empty",
        "metadata": {"content_type": {}, "attributes": {}},
    }),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["capture", "factory", "service"])
@pytest.mark.parametrize("error_type", [RuntimeError, ToolError])
@pytest.mark.parametrize("tool,operation,arguments", TOOL_OPERATIONS)
async def test_unmasked_tools_sanitize_all_operation_stages(
    filesystem_error_context: FilesystemErrorContext, stage: str, error_type: type[Exception],
    tool: str, operation: str, arguments: dict[str, Any],
) -> None:
    application_failures = create_application_failure_signal()
    server = FastMCP()
    error = error_type("SECRET backend /private/path")
    callers = Mock(spec=FilesystemCallerCapture)
    callers.capture.return_value = filesystem_error_context.callers.capture()
    service_type = {
        "check_delete_eligibility": FilesystemDeletion,
        "create_file": FilesystemCreation,
        "create_directory": FilesystemCreation,
    }.get(operation, FilesystemBrowsing)
    service = Mock(spec=service_type)
    setattr(service, operation, AsyncMock(side_effect=error))
    factory = Mock(spec=FilesystemServiceFactory)
    factory_method = {
        "check_delete_eligibility": factory.deletion,
        "create_file": factory.creation,
        "create_directory": factory.creation,
    }.get(operation, factory.browsing)
    factory_method.return_value = service
    if stage == "capture":
        callers.capture.side_effect = error
    if stage == "factory":
        factory_method.side_effect = error
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(create_mcp_signals(Mock(), filesystem_error_context.metrics, Mock(), application_failures=application_failures))),
        callers, factory, filesystem_error_context.visibility, filesystem_error_context.approval,
    )
    async with Client(server) as client:
        result = await client.call_tool(tool, arguments, raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == "filesystem_operation_failed: Filesystem operation failed."
    guidance = result.meta["computerlove.tech/umbod"]["guidance"]
    assert guidance["operation_state"] == ("not_started" if tool == "filesystem_delete_file" else "unknown")
    assert guidance["recovery"]["retry"] == "inspect_before_retry"
    assert guidance["recovery"]["instructions"]
    for instruction in guidance["recovery"]["instructions"]:
        assert instruction in result.content[1].text
    assert "SECRET" not in result.content[0].text
    assert "/private/path" not in result.content[0].text


def test_cancellation_propagates_without_translation() -> None:
    with pytest.raises(asyncio.CancelledError):
        with filesystem_operation():
            raise asyncio.CancelledError()
