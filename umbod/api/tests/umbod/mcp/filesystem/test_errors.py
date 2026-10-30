import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from umbod.core.filesystem.authorization.errors import PermissionDenied
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.creation import FilesystemCreation
from umbod.core.filesystem.content import FilesystemContent
from umbod.core.filesystem.deletion import FilesystemDeletion
from umbod.core.filesystem.sharing import InvalidSharingPolicy, SharingPolicyUnavailable
from umbod.core.filesystem.content.errors import UploadTooLarge
from umbod.core.filesystem.uploads.errors import (
    UploadConflict, UploadExpired, UploadLengthMismatch, UploadMediaTypeMismatch,
)
from umbod.core.filesystem.errors import InvalidName, MissingNode, NameCollision, RevisionConflict, StorageFailure, WrongNodeKind
from umbod.mcp.filesystem import register_filesystem_tools
from umbod.mcp.filesystem.errors import filesystem_operation
from umbod.mcp.filesystem.ports import FilesystemCallerCapture, FilesystemServiceFactory
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.signals import McpInvocationPublisher
from .conftest import FilesystemMcp


class SpecializedStorageFailure(StorageFailure):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type,expected", [
    (InvalidSharingPolicy, "filesystem_invalid_sharing_policy: Invalid filesystem sharing policy"),
    (SharingPolicyUnavailable, "filesystem_policy_unavailable: Filesystem sharing configuration unavailable"),
    (UploadTooLarge, "filesystem_upload_too_large: Filesystem upload too large"),
    (UploadConflict, "filesystem_upload_conflict: Filesystem upload conflict"),
    (UploadExpired, "filesystem_upload_expired: Filesystem upload expired"),
    (UploadLengthMismatch, "filesystem_upload_length_mismatch: Invalid upload length"),
    (UploadMediaTypeMismatch, "filesystem_upload_media_type_mismatch: Invalid upload content type"),
    (PermissionDenied, "filesystem_permission_denied: Filesystem access denied"),
    (MissingNode, "filesystem_permission_denied: Filesystem access denied"),
    (InvalidName, "filesystem_invalid_name: Invalid filesystem name"),
    (NameCollision, "filesystem_name_collision: Filesystem name already exists"),
    (RevisionConflict, "filesystem_revision_conflict: Filesystem revision conflict"),
    (WrongNodeKind, "filesystem_wrong_node_kind: Invalid filesystem node kind"),
    (StorageFailure, "filesystem_storage_failure: Filesystem storage unavailable"),
    (SpecializedStorageFailure, "filesystem_storage_failure: Filesystem storage unavailable"),
])
async def test_expected_domain_failures_do_not_leak_details(
    filesystem_mcp: FilesystemMcp, error_type: type[Exception], expected: str,
) -> None:
    server = FastMCP()
    browsing = Mock(spec=FilesystemBrowsing)
    browsing.get_root = AsyncMock(side_effect=error_type("SECRET backend /private/path"))
    factory = Mock(spec=FilesystemServiceFactory)
    factory.browsing.return_value = browsing
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(create_mcp_signals(Mock(), filesystem_mcp.metrics, Mock()))),
        filesystem_mcp.callers, factory,
    )
    async with Client(server) as client:
        result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == expected
    assert any(sample.labels["outcome"] == "failure" for sample in filesystem_mcp.metrics.metric_samples())


TOOL_OPERATIONS = [
    ("filesystem_read_file", "open_download", {
        "node_id": "00000000-0000-0000-0000-000000000001", "encoding": "utf-8", "max_bytes": 1_048_576,
    }),
    ("filesystem_delete_file", "delete_file", {
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
    filesystem_mcp: FilesystemMcp, stage: str, error_type: type[Exception],
    tool: str, operation: str, arguments: dict[str, Any],
) -> None:
    server = FastMCP()
    error = error_type("SECRET backend /private/path")
    callers = Mock(spec=FilesystemCallerCapture)
    callers.capture.return_value = filesystem_mcp.callers.capture()
    service_type = {
        "open_download": FilesystemContent,
        "delete_file": FilesystemDeletion,
        "create_file": FilesystemCreation,
        "create_directory": FilesystemCreation,
    }.get(operation, FilesystemBrowsing)
    service = Mock(spec=service_type)
    setattr(service, operation, AsyncMock(side_effect=error))
    factory = Mock(spec=FilesystemServiceFactory)
    factory_method = {
        "open_download": factory.content,
        "delete_file": factory.deletion,
        "create_file": factory.creation,
        "create_directory": factory.creation,
    }.get(operation, factory.browsing)
    factory_method.return_value = service
    if stage == "capture":
        callers.capture.side_effect = error
    if stage == "factory":
        factory_method.side_effect = error
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(create_mcp_signals(Mock(), filesystem_mcp.metrics, Mock()))),
        callers, factory,
    )
    async with Client(server) as client:
        result = await client.call_tool(tool, arguments, raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == "filesystem_operation_failed: Filesystem operation failed"
    assert "SECRET" not in result.content[0].text
    assert "/private/path" not in result.content[0].text


def test_cancellation_propagates_without_translation() -> None:
    with pytest.raises(asyncio.CancelledError):
        with filesystem_operation():
            raise asyncio.CancelledError()
