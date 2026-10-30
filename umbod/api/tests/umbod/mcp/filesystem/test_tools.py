import asyncio
from typing import Any
from uuid import uuid4

import pytest
from fastmcp import Client

from umbod.core.callers import AuthenticationProvenance
from umbod.mcp.tools.registration import ObservedFunctionTool
from .conftest import FilesystemMcp, caller_snapshot

METADATA = {"content_type": {}, "attributes": {}}
CREATE = "create_filesystem_file"


async def root_id(client: Client) -> str:
    return str((await client.call_tool("get_filesystem_root", {})).data.id)


@pytest.mark.asyncio
async def test_observed_tools_publish_safe_schemas(filesystem_mcp: FilesystemMcp) -> None:
    tools = await filesystem_mcp.server.list_tools()
    assert len(tools) == 9
    assert all(isinstance(tool, ObservedFunctionTool) for tool in tools)
    async with Client(filesystem_mcp.server) as client:
        descriptors = {tool.name: tool for tool in await client.list_tools()}
    assert set(descriptors) == {
        "filesystem_browse", "get_filesystem_root", "get_filesystem_node", "list_filesystem_children",
        "create_filesystem_file", "create_filesystem_directory", "filesystem_upload", "filesystem_delete_file",
        "filesystem_read_file",
    }
    schema = descriptors[CREATE].input_schema
    assert set(schema["properties"]) == {"parent_id", "name", "metadata"}
    assert set(schema["required"]) == {"parent_id", "name", "metadata"}
    assert schema["properties"]["parent_id"]["format"] == "uuid"
    for name, tool in descriptors.items():
        mutation = name.startswith("create_") or name in {"filesystem_upload", "filesystem_delete_file"}
        assert tool.annotations.read_only_hint == (not mutation)
        assert tool.annotations.idempotent_hint == (not mutation)
    assert "content" not in descriptors[CREATE].output_schema["properties"]
    assert "owner" not in descriptors[CREATE].output_schema["properties"]


@pytest.mark.asyncio
async def test_bootstrap_group_can_create_private_nodes_and_filter_children(
    filesystem_mcp: FilesystemMcp,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        created = await client.call_tool(CREATE, {"parent_id": root, "name": "private", "metadata": METADATA})
        child_id = str(created.data.id)
        assert created.data.name == "private"
        assert (await client.call_tool("get_filesystem_node", {"node_id": child_id})).data.id == created.data.id
        filesystem_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED
        ))
        listed = await client.call_tool("list_filesystem_children", {"parent_id": root})
        assert listed.structured_content == {"nodes": []}
        denied = await client.call_tool("get_filesystem_node", {"node_id": child_id}, raise_on_error=False)
        missing = await client.call_tool("get_filesystem_node", {"node_id": str(uuid4())}, raise_on_error=False)
        assert denied.content == missing.content
        assert "filesystem_permission_denied" in denied.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["create_filesystem_file", "create_filesystem_directory"])
async def test_creation_is_observed_and_projects_no_storage_keys(
    filesystem_mcp: FilesystemMcp, tool: str,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        result = await client.call_tool(tool, {"parent_id": root, "name": "empty", "metadata": METADATA})
        assert set(result.structured_content) == {
            "id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision"
        }
    assert any(sample.labels["tool_name"] == tool and sample.labels["outcome"] == "success"
               for sample in filesystem_mcp.metrics.metric_samples())


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", [
    AuthenticationProvenance.LOCAL_TEST, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    AuthenticationProvenance.LOCAL_SIMULATION, AuthenticationProvenance.LOCAL_SEMANTIC,
])
async def test_nonverified_callers_remain_denied(
    filesystem_mcp: FilesystemMcp, provenance: AuthenticationProvenance,
) -> None:
    filesystem_mcp.callers.current.set(caller_snapshot("alice", "https://issuer", ("writers",), provenance))
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)
    assert result.is_error
    assert "filesystem_permission_denied" in result.content[0].text


@pytest.mark.asyncio
async def test_same_group_identifier_from_other_issuer_has_no_access(filesystem_mcp: FilesystemMcp) -> None:
    filesystem_mcp.callers.current.set(caller_snapshot(
        "alice", "https://other-issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED
    ))
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)
    assert result.is_error


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {"parent_id": "not-a-uuid", "name": "file", "metadata": METADATA},
    {"name": "file"},
    {"name": "file", "metadata": METADATA, "owner": "alice"},
    {"name": "file", "metadata": METADATA, "caller": {}},
    {"name": "file", "metadata": METADATA, "grants": []},
    {"name": "file", "metadata": METADATA, "content": "secret"},
])
async def test_invalid_body_and_authority_injection_are_rejected(
    filesystem_mcp: FilesystemMcp, arguments: dict[str, Any],
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        result = await client.call_tool(CREATE, {"parent_id": root, **arguments}, raise_on_error=False)
    assert result.is_error


@pytest.mark.asyncio
async def test_filesystem_invalid_names_and_collisions_have_fixed_errors(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        invalid = await client.call_tool(CREATE, {"parent_id": root, "name": "../sensitive", "metadata": METADATA}, raise_on_error=False)
        assert invalid.content[0].text == "filesystem_invalid_name: Invalid filesystem name"
        await client.call_tool(CREATE, {"parent_id": root, "name": "duplicate", "metadata": METADATA})
        collision = await client.call_tool(CREATE, {"parent_id": root, "name": "duplicate", "metadata": METADATA}, raise_on_error=False)
        assert collision.content[0].text == "filesystem_name_collision: Filesystem name already exists"


@pytest.mark.asyncio
async def test_concurrent_callers_and_later_membership_revocation_are_isolated(
    filesystem_mcp: FilesystemMcp,
) -> None:
    async def invoke(groups: tuple[str, ...]) -> bool:
        filesystem_mcp.callers.current.set(caller_snapshot(
            "alice", "https://issuer", groups, AuthenticationProvenance.UPSTREAM_VERIFIED
        ))
        async with Client(filesystem_mcp.server) as client:
            return (await client.call_tool("get_filesystem_root", {}, raise_on_error=False)).is_error

    assert await asyncio.gather(invoke(("writers",)), invoke(())) == [False, True]
    assert await invoke(()) is True
    assert filesystem_mcp.callers.count == 3
