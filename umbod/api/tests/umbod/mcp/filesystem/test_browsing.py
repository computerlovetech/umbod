from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastmcp import Client, FastMCP
from jsonschema import validate

from umbod.core.callers import AuthenticationProvenance
from umbod.mcp.filesystem import register_filesystem_tools
from umbod.mcp.signals import McpInvocationPublisher
from umbod.mcp.tools import McpObservedToolRegistrar

from .conftest import FilesystemMcp, caller_snapshot
from .test_tools import METADATA, root_id

TOOL = "filesystem_browse"
ROOT = {"type": "root"}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["ls", "tree", "stat", "unknown"])
async def test_browse_observation_records_only_declared_operation_names(
    filesystem_mcp: FilesystemMcp, operation: str,
) -> None:
    server = FastMCP()
    publisher = Mock(spec=McpInvocationPublisher)
    register_filesystem_tools(
        McpObservedToolRegistrar(server, publisher), filesystem_mcp.callers, filesystem_mcp.services,
    )
    async with Client(server) as client:
        result = await client.call_tool(TOOL, {"operation": operation, "target": ROOT}, raise_on_error=False)
    identity = publisher.start.call_args.args[0]
    assert identity.tool_name == TOOL
    assert identity.operation_name == (operation if operation != "unknown" else None)
    assert result.is_error == (operation == "unknown")
    if result.is_error:
        publisher.failed.assert_called_once()
    else:
        publisher.succeeded.assert_called_once()


async def create_node(client: Client, parent: str, name: str, kind: str) -> str:
    result = await client.call_tool(f"create_filesystem_{kind}", {
        "parent_id": parent, "name": name, "metadata": METADATA,
    })
    return str(result.structured_content["id"])


@pytest.mark.asyncio
async def test_browse_discovery_declares_operations_without_constructing_services(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = Mock(side_effect=AssertionError("Discovery must not access services"))
    monkeypatch.setattr(filesystem_mcp.services, "browsing", factory)
    async with Client(filesystem_mcp.server) as client:
        descriptor = next(tool for tool in await client.list_tools() if tool.name == TOOL)
    assert descriptor.input_schema["type"] == "object"
    branches = descriptor.input_schema["oneOf"]
    assert {branch["properties"]["operation"]["const"] for branch in branches} == {"ls", "tree", "stat"}
    assert all(branch["additionalProperties"] is False for branch in branches)
    assert all(branch["properties"]["target"] == {} for branch in branches)
    assert len(descriptor.input_schema["properties"]["target"]["oneOf"]) == 3
    assert descriptor.annotations.read_only_hint is True
    assert descriptor.annotations.destructive_hint is False
    assert descriptor.annotations.idempotent_hint is True
    assert descriptor.output_schema["type"] == "object"
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_listing_root_is_one_invocation_with_context_and_structured_entries(
    filesystem_mcp: FilesystemMcp,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        directory = await create_node(client, root, "projects", "directory")
        await create_node(client, root, "notes.txt", "file")
        captures = filesystem_mcp.callers.count
        result = await client.call_tool(TOOL, {"operation": "ls", "target": ROOT})
        descriptor = next(tool for tool in await client.list_tools() if tool.name == TOOL)
    assert filesystem_mcp.callers.count == captures + 1
    validate(result.structured_content, descriptor.output_schema)
    listing = result.structured_content["result"]
    assert listing["node"]["id"] == root
    assert listing["breadcrumbs"]["complete"] is True
    assert [node["name"] for node in listing["entries"]] == ["projects", "notes.txt"]
    assert listing["entries"][0]["id"] == directory
    assert listing["truncated"] is False
    assert '"projects"/' in result.content[0].text
    assert any(sample.labels["tool_name"] == TOOL and sample.labels["outcome"] == "success" and sample.value > 0
               for sample in filesystem_mcp.metrics.metric_samples())


@pytest.mark.asyncio
async def test_tree_resolves_path_and_returns_descendants_with_depth_cutoffs(
    filesystem_mcp: FilesystemMcp,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        projects = await create_node(client, root, "projects", "directory")
        reports = await create_node(client, projects, "reports", "directory")
        await create_node(client, reports, "annual.txt", "file")
        result = await client.call_tool(TOOL, {
            "operation": "tree", "target": {"type": "path", "path": "/projects"}, "depth": 1,
        })
    tree = result.structured_content["result"]
    assert tree["node"]["id"] == projects
    assert [entry["node"]["name"] for entry in tree["entries"]] == ["reports"]
    assert tree["entries"][0]["expansion"] == "depth_limit"
    assert "[depth_limit]" in result.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["ls", "tree"])
async def test_browse_entry_limits_are_explicit(filesystem_mcp: FilesystemMcp, operation: str) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        await create_node(client, root, "a", "file")
        await create_node(client, root, "b", "file")
        result = await client.call_tool(TOOL, {"operation": operation, "target": ROOT, "max_entries": 1})
    listing = result.structured_content["result"]
    assert len(listing["entries"]) == 1
    assert "incomplete" in result.content[0].text
    if operation == "ls":
        assert listing["truncated"] is True
    else:
        assert listing["expansion"] == "entry_limit"


@pytest.mark.asyncio
async def test_stat_accepts_file_id_without_reading_bytes(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        node_id = await create_node(client, root, "notes.txt", "file")
        result = await client.call_tool(TOOL, {
            "operation": "stat", "target": {"type": "node", "node_id": node_id},
        })
    inspection = result.structured_content["result"]
    assert inspection["node"]["kind"] == "file"
    assert inspection["node"]["revision"] == 1
    assert "content" not in inspection["node"]
    assert "owner" not in inspection["node"]
    assert '"/notes.txt"' in result.content[0].text


@pytest.mark.asyncio
async def test_independently_accessible_directory_by_id_preserves_partial_location(
    filesystem_mcp: FilesystemMcp,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        directory = await create_node(client, root, "private", "directory")
        filesystem_mcp.callers.current.set(caller_snapshot(
            "alice", "https://issuer", (), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        result = await client.call_tool(TOOL, {
            "operation": "ls", "target": {"type": "node", "node_id": directory},
        })
        denied = await client.call_tool(TOOL, {
            "operation": "ls", "target": {"type": "path", "path": "/private"},
        }, raise_on_error=False)
    assert result.structured_content["result"]["breadcrumbs"]["complete"] is False
    assert '".../private"' in result.content[0].text
    assert denied.is_error
    assert denied.content[0].text == "filesystem_permission_denied: Filesystem access denied"


@pytest.mark.asyncio
async def test_browse_filters_other_owners_and_hides_path_existence(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        await create_node(client, root, "private", "directory")
        filesystem_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        listing = await client.call_tool(TOOL, {"operation": "tree", "target": ROOT})
        hidden = await client.call_tool(TOOL, {
            "operation": "stat", "target": {"type": "path", "path": "/private"},
        }, raise_on_error=False)
        missing = await client.call_tool(TOOL, {
            "operation": "stat", "target": {"type": "path", "path": "/missing"},
        }, raise_on_error=False)
    assert listing.structured_content["result"]["entries"] == []
    assert hidden.content == missing.content


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {},
    {"operation": "cd", "target": ROOT},
    {"operation": "ls", "target": ROOT, "depth": 2},
    {"operation": "stat", "target": ROOT, "max_entries": 10},
    {"operation": "ls", "target": ROOT, "owner": "alice"},
    {"operation": "ls", "target": {"type": "root", "node_id": str(uuid4())}},
    {"operation": "ls", "target": {"type": "node", "node_id": "invalid"}},
    {"operation": "ls", "target": {"type": "path", "path": "relative"}},
    {"operation": "ls", "target": {"type": "path", "path": "/../secret"}},
    {"operation": "ls", "target": ROOT, "max_entries": True},
    {"operation": "ls", "target": ROOT, "max_entries": "10"},
    {"operation": "ls", "target": ROOT, "max_entries": 1001},
    {"operation": "tree", "target": ROOT, "depth": 0},
    {"operation": "tree", "target": ROOT, "depth": 17},
])
async def test_browse_rejects_invalid_commands_before_caller_capture(
    filesystem_mcp: FilesystemMcp, arguments: dict[str, Any],
) -> None:
    captures = filesystem_mcp.callers.count
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool(TOOL, arguments, raise_on_error=False)
    assert result.is_error
    assert filesystem_mcp.callers.count == captures


@pytest.mark.asyncio
async def test_listing_file_returns_existing_safe_kind_error(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        node_id = await create_node(client, root, "file", "file")
        result = await client.call_tool(TOOL, {
            "operation": "ls", "target": {"type": "node", "node_id": node_id},
        }, raise_on_error=False)
    assert result.content[0].text == "filesystem_wrong_node_kind: Invalid filesystem node kind"
