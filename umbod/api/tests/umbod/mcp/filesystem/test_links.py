import json
from typing import Any
from uuid import UUID

import pytest
from fastmcp import Client
from mcp.types import ResourceLink, TextResourceContents

from umbod.mcp.filesystem.links import file_resource_uri

from .conftest import FilesystemMcp
from .test_tools import METADATA, root_id


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["create_filesystem_file", "filesystem_upload"])
async def test_file_publication_returns_native_resource_link_without_content(
    filesystem_invocation_mcp: FilesystemMcp, tool: str,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        arguments: dict[str, Any] = {"parent_id": await root_id(client), "name": "report.txt", "metadata": {
            "content_type": "text/plain", "attributes": {},
        }}
        if tool == "filesystem_upload":
            arguments["content"] = {"encoding": "utf-8", "text": "private content"}
        result = await client.call_tool(tool, arguments)
    links = [content for content in result.content if isinstance(content, ResourceLink)]
    assert len(links) == 1
    assert links[0].uri == file_resource_uri(UUID(result.structured_content["id"]))
    assert links[0].name == "report.txt"
    assert links[0].mime_type == "text/plain"
    assert "private content" not in json.dumps({
        "content": [content.model_dump() for content in result.content],
        "structured": result.structured_content,
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["ls", "tree", "stat", "get", "children"])
async def test_file_discovery_returns_native_resource_links(
    filesystem_invocation_mcp: FilesystemMcp, operation: str,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        root = await root_id(client)
        created = await client.call_tool("create_filesystem_file", {
            "parent_id": root, "name": "report", "metadata": METADATA,
        })
        node_id = created.structured_content["id"]
        if operation == "get":
            result = await client.call_tool("get_filesystem_node", {"node_id": node_id})
        elif operation == "children":
            result = await client.call_tool("list_filesystem_children", {"parent_id": root})
        else:
            target = {"type": "node", "node_id": node_id if operation == "stat" else root}
            arguments: dict[str, Any] = {"operation": operation, "target": target}
            if operation in {"ls", "tree"}:
                arguments["max_entries"] = 10
            if operation == "tree":
                arguments["depth"] = 2
            result = await client.call_tool("filesystem_browse", arguments)
    links = [content for content in result.content if isinstance(content, ResourceLink)]
    assert [link.uri for link in links] == [file_resource_uri(UUID(node_id))]
    assert links[0].mime_type == "application/octet-stream"


@pytest.mark.asyncio
async def test_directories_do_not_return_file_resource_links(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool("create_filesystem_directory", {
            "parent_id": await root_id(client), "name": "folder", "metadata": METADATA,
        })
    assert not any(isinstance(content, ResourceLink) for content in result.content)


@pytest.mark.asyncio
async def test_uploaded_resource_link_reads_content_before_discovery_reconciliation(
    filesystem_mcp: FilesystemMcp,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        uploaded = await client.call_tool("filesystem_upload", {
            "parent_id": await root_id(client), "name": "report.txt",
            "metadata": {"content_type": "text/plain", "attributes": {}},
            "content": {"encoding": "utf-8", "text": "file content"},
        })
        link = next(content for content in uploaded.content if isinstance(content, ResourceLink))
        contents = await client.read_resource(link.uri)
    assert len(contents) == 1
    assert isinstance(contents[0], TextResourceContents)
    assert contents[0].text == "file content"
