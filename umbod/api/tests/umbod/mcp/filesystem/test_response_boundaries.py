import json
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import AuthorizationError
from mcp.shared.exceptions import MCPError

from tests.support.signals import InMemorySignalFailureHandler
from umbod.core.filesystem.sharing import FilesystemSharing, SharingRecipientSearchResult
from umbod.core.filesystem.uploads.errors import (
    UploadChecksumMismatch, UploadConflict, UploadExpired, UploadLengthMismatch, UploadReceiptUnavailable,
)
from umbod.core.responses import ToolFailureMetadata
from umbod.infrastructure import create_access_control_driver, create_namespace_driver
from umbod.mcp.filesystem import register_filesystem_tools
from umbod.mcp.filesystem.deletion import FilesystemDeleteFileTool
from umbod.mcp.filesystem.errors import filesystem_operation
from umbod.mcp.filesystem.ports import FilesystemServiceFactory
from umbod.mcp.responses.adapter import RESPONSE_METADATA_KEY
from umbod.mcp.signals import McpInvocationPublisher, McpSignals
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.tools.errors import BuiltinToolError

from .conftest import FilesystemMcp, FilesystemState
from .test_approval import ApprovalContext
from .test_browsing import create_node
from .test_tools import root_id


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,operation", [
    ("get_filesystem_root", ""),
    ("get_filesystem_node", ""),
    ("list_filesystem_children", ""),
    ("filesystem_browse", "stat"),
    ("filesystem_browse", "tree"),
    ("filesystem_browse", "ls"),
    ("filesystem_search_sharing_recipients", ""),
])
async def test_primary_read_completion_survives_enrichment_or_serialization_failure(
    filesystem_state: FilesystemState, tool_name: str, operation: str,
) -> None:
    filesystem = filesystem_state
    browsing = filesystem.services.browsing()
    root = await browsing.get_root(filesystem.callers.capture())
    sharing = Mock(spec=FilesystemSharing)
    sharing.summarize_nodes = AsyncMock(side_effect=RuntimeError("SECRET enrichment failure"))
    recipients = Mock(spec=SharingRecipientSearchResult)
    recipients.model_dump_json.side_effect = RuntimeError("SECRET serialization failure")
    sharing.search_recipients = AsyncMock(return_value=recipients)
    services = Mock(spec=FilesystemServiceFactory)
    services.browsing.return_value = browsing
    services.access.return_value = filesystem.services.access()
    services.sharing.return_value = sharing
    server = FastMCP()
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(McpSignals(InMemorySignalFailureHandler()))),
        filesystem.callers, services, filesystem.visibility, filesystem.approval,
    )
    arguments: dict[str, Any] = {}
    if operation:
        arguments = {"operation": operation, "target": {"type": "root"}}
    elif tool_name == "get_filesystem_node":
        arguments = {"node_id": str(root.id)}
    elif tool_name == "list_filesystem_children":
        arguments = {"parent_id": str(root.id)}
    elif tool_name == "filesystem_search_sharing_recipients":
        arguments = {"node_id": str(root.id), "query": "writers"}
    async with Client(server) as client:
        result = await client.call_tool(tool_name, arguments, raise_on_error=False)
    assert result.is_error
    metadata = ToolFailureMetadata.model_validate(result.meta[RESPONSE_METADATA_KEY])
    assert metadata.schema_version == 1
    assert metadata.guidance.operation_state == "completed"
    assert metadata.guidance.recovery.retry == "inspect_before_retry"
    assert metadata.guidance.error.message == "Filesystem operation failed."
    assert "SECRET" not in json.dumps({
        "meta": result.meta, "content": [item.model_dump(mode="json") for item in result.content],
    })
    if tool_name == "filesystem_search_sharing_recipients":
        sharing.search_recipients.assert_awaited_once()
        recipients.model_dump_json.assert_called_once()
    else:
        sharing.summarize_nodes.assert_awaited_once()


@pytest.mark.parametrize("error_type,summary", [
    (UploadConflict, "Filesystem upload conflict."),
    (UploadExpired, "Filesystem upload expired."),
    (UploadChecksumMismatch, "Upload checksum does not match."),
    (UploadLengthMismatch, "Invalid upload length."),
    (UploadReceiptUnavailable, "Legacy upload has no verified receipt."),
])
def test_upload_failure_details_leave_recovery_to_shared_guidance(
    error_type: type[Exception], summary: str,
) -> None:
    with pytest.raises(BuiltinToolError) as raised:
        with filesystem_operation():
            raise error_type()
    assert raised.value.details.message == summary


@pytest.mark.asyncio
@pytest.mark.parametrize("error_kind", ["protocol", "authorization"])
async def test_native_approval_failure_passes_through_unchanged_without_deletion(
    filesystem_invocation_mcp: FilesystemMcp, error_kind: str,
) -> None:
    filesystem = filesystem_invocation_mcp
    async with Client(filesystem.server) as client:
        node_id = await create_node(client, await root_id(client), "native-approval-target", "file")
    namespace = create_namespace_driver(database=filesystem.database)
    policies = create_access_control_driver(database=filesystem.database)
    before = await namespace.get_node(UUID(node_id))
    owner = await policies.get_owner(UUID(node_id))
    grants = await policies.list_grants(UUID(node_id))
    error = (
        MCPError(-32603, "Native protocol failure")
        if error_kind == "protocol" else AuthorizationError("Native authorization failure")
    )
    context = ApprovalContext(False)
    context.response = error
    tool = FilesystemDeleteFileTool(filesystem.callers, filesystem.services, filesystem.approval)
    async with context:
        with pytest.raises(type(error)) as raised:
            await tool.run({"node_id": node_id, "expected_revision": before.revision})
    assert raised.value is error
    assert await namespace.get_node(UUID(node_id)) == before
    assert await policies.get_owner(UUID(node_id)) == owner
    assert await policies.list_grants(UUID(node_id)) == grants
    assert len(context.elicitations) == 1
