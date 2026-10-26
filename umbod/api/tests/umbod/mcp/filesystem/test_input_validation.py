from typing import Any

import pytest
from fastmcp import Client

from .conftest import FilesystemMcp
from .test_tools import METADATA, root_id


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["create_filesystem_file", "create_filesystem_directory"])
@pytest.mark.parametrize("extra", [
    {"owner": "injected"}, {"caller": {}}, {"grants": []}, {"content": "SECRET"},
])
async def test_otherwise_valid_creation_rejects_authority_extras_without_creating_nodes(
    filesystem_mcp: FilesystemMcp, tool: str, extra: dict[str, Any],
) -> None:
    async with Client(filesystem_mcp.server) as client:
        parent = await root_id(client)
        captures_before = filesystem_mcp.callers.count
        result = await client.call_tool(tool, {
            "parent_id": parent, "name": "must-not-exist", "metadata": METADATA, **extra,
        }, raise_on_error=False)
        assert result.is_error
        assert filesystem_mcp.callers.count == captures_before
        children = await client.call_tool("list_filesystem_children", {"parent_id": parent})
        assert children.structured_content == {"nodes": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [
    "get_filesystem_root", "get_filesystem_node", "list_filesystem_children",
])
@pytest.mark.parametrize("extra", [
    {"owner": "injected"}, {"caller": {}}, {"grants": []}, {"content": "SECRET"},
])
async def test_browsing_rejects_extras_before_invocation(
    filesystem_mcp: FilesystemMcp, tool: str, extra: dict[str, Any],
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        arguments = {
            "get_filesystem_root": {},
            "get_filesystem_node": {"node_id": root},
            "list_filesystem_children": {"parent_id": root},
        }[tool]
        captures_before = filesystem_mcp.callers.count
        result = await client.call_tool(tool, {**arguments, **extra}, raise_on_error=False)
        assert result.is_error
        assert filesystem_mcp.callers.count == captures_before


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["create_filesystem_file", "create_filesystem_directory"])
@pytest.mark.parametrize("extra", [
    {"owner": "injected"}, {"caller": {}}, {"grants": []},
    {"content": "SECRET"}, {"key": "/private/path"},
])
async def test_creation_metadata_rejects_undeclared_fields(
    filesystem_mcp: FilesystemMcp, tool: str, extra: dict[str, Any],
) -> None:
    async with Client(filesystem_mcp.server) as client:
        parent = await root_id(client)
        captures_before = filesystem_mcp.callers.count
        result = await client.call_tool(tool, {
            "parent_id": parent, "name": "must-not-exist", "metadata": {**METADATA, **extra},
        }, raise_on_error=False)
        assert result.is_error
        assert filesystem_mcp.callers.count == captures_before
        children = await client.call_tool("list_filesystem_children", {"parent_id": parent})
        assert children.structured_content == {"nodes": []}


@pytest.mark.asyncio
async def test_authority_named_metadata_attributes_are_only_data(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        parent = await root_id(client)
        result = await client.call_tool("create_filesystem_file", {
            "parent_id": parent, "name": "ordinary",
            "metadata": {"content_type": {}, "attributes": {"owner": "bob", "key": "value"}},
        })
        assert result.structured_content["metadata"]["attributes"] == {"owner": "bob", "key": "value"}
        assert "owner" not in result.structured_content
