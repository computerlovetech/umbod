import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import Client, FastMCP

from tests.support.signals import InMemorySignalFailureHandler
from umbod.core.filesystem.sharing import FilesystemSharing
from umbod.core.responses import ToolFailureMetadata
from umbod.mcp.filesystem import register_filesystem_tools
from umbod.mcp.filesystem.ports import FilesystemServiceFactory
from umbod.mcp.responses.adapter import RESPONSE_METADATA_KEY
from umbod.mcp.signals import McpInvocationPublisher, McpSignals
from umbod.mcp.tools import McpObservedToolRegistrar

from .conftest import FilesystemMcp


@pytest.mark.parametrize("tool_name", ["create_filesystem_file", "create_filesystem_directory"])
@pytest.mark.asyncio
async def test_legacy_create_enrichment_failure_reports_completed_without_duplicate_write(
    filesystem_invocation_mcp: FilesystemMcp, tool_name: str,
) -> None:
    filesystem = filesystem_invocation_mcp
    caller = filesystem.callers.capture()
    browsing = filesystem.services.browsing()
    root = await browsing.get_root(caller)
    sharing = Mock(spec=FilesystemSharing)
    sharing.summarize_nodes = AsyncMock(side_effect=RuntimeError("SECRET enrichment payload"))
    services = Mock(spec=FilesystemServiceFactory)
    services.browsing.return_value = browsing
    services.creation.return_value = filesystem.services.creation()
    services.access.return_value = filesystem.services.access()
    services.sharing.return_value = sharing
    server = FastMCP()
    signals = McpSignals(InMemorySignalFailureHandler())
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(signals)),
        filesystem.callers, services, filesystem.visibility, filesystem.approval,
    )

    async with Client(server) as client:
        result = await client.call_tool(tool_name, {
            "parent_id": str(root.id), "name": "file",
            "metadata": {"content_type": {}, "attributes": {}},
        }, raise_on_error=False)

    assert result.is_error
    metadata = result.meta[RESPONSE_METADATA_KEY]
    validated = ToolFailureMetadata.model_validate(metadata)
    assert validated.schema_version == 1
    assert validated.request_id
    assert validated.guidance.outcome == "failure"
    assert validated.guidance.operation_state == "completed"
    assert validated.guidance.recovery.retry == "inspect_before_retry"
    assert validated.guidance.error.code == "filesystem_operation_failed"
    assert validated.guidance.error.issues == ()
    assert "SECRET" not in json.dumps({
        "meta": result.meta,
        "content": [item.model_dump(mode="json") for item in result.content],
        "structured_content": result.structured_content,
    })
    children = await browsing.list_children(caller, root.id)
    assert [node.name for node in children] == ["file"]
    sharing.summarize_nodes.assert_awaited_once()


@pytest.mark.asyncio
async def test_home_enrichment_failure_retains_completed_provisioning(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    filesystem = filesystem_invocation_mcp
    homes = filesystem.services.homes()
    provisioning = AsyncMock(wraps=homes.get_or_provision)
    sharing = Mock(spec=FilesystemSharing)
    sharing.summarize_nodes = AsyncMock(side_effect=RuntimeError("SECRET home enrichment"))
    services = Mock(spec=FilesystemServiceFactory)
    services.browsing.return_value = filesystem.services.browsing()
    services.access.return_value = filesystem.services.access()
    services.homes.return_value = Mock(get_or_provision=provisioning)
    services.sharing.return_value = sharing
    server = FastMCP()
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(McpSignals(InMemorySignalFailureHandler()))),
        filesystem.callers, services, filesystem.visibility, filesystem.approval,
    )
    async with Client(server) as client:
        result = await client.call_tool("filesystem_browse", {"operation": "home"}, raise_on_error=False)
    validated = ToolFailureMetadata.model_validate(result.meta[RESPONSE_METADATA_KEY])
    assert validated.guidance.operation_state == "completed"
    assert validated.guidance.recovery.retry == "inspect_before_retry"
    assert "SECRET" not in repr(result)
    provisioning.assert_awaited_once()
    sharing.summarize_nodes.assert_awaited_once()
