import json
from uuid import UUID

import pytest
from fastmcp import Client
from jsonschema import validate
from mcp.types import ResourceLink

from umbod.core.filesystem import Permission
from .conftest import FilesystemMcp
from .test_browsing import create_node
from .test_tools import root_id
from .test_visibility import grant, listed_tools, private_node, select_caller

TOOL = "update_filesystem_node"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "directory"])
async def test_node_update_schema_description_browsing_clearing_and_stale_revision(
    filesystem_invocation_mcp: FilesystemMcp, kind: str,
) -> None:
    filesystem = filesystem_invocation_mcp
    description = 'What is here\nforged row\r"when to read"'
    async with Client(filesystem.server) as client:
        node_id = await create_node(client, await root_id(client), "described", kind)
        tools = await client.list_tools()
        assert "update_filesystem_description" not in {tool.name for tool in tools}
        descriptor = next(tool for tool in tools if tool.name == TOOL)
        assert descriptor.input_schema["required"] == ["node_id", "expected_revision"]
        assert descriptor.input_schema["properties"]["expected_revision"]["minimum"] == 1
        assert "when to read" in json.dumps(descriptor.input_schema)
        assert descriptor.annotations.read_only_hint is False
        assert descriptor.annotations.destructive_hint is False
        assert descriptor.annotations.idempotent_hint is False
        assert descriptor.annotations.open_world_hint is False
        arguments = {
            "node_id": node_id, "metadata": {"attributes": {"description": description, "team": "research"}},
            "expected_revision": 1,
        }
        validate(arguments, descriptor.input_schema)
        updated = await client.call_tool(TOOL, arguments)
        validate(updated.structured_content, descriptor.output_schema)
        node = updated.structured_content
        assert node["metadata"]["attributes"] == {"description": description, "team": "research"}
        assert node["revision"] == 2
        assert any(isinstance(item, ResourceLink) for item in updated.content) == (kind == "file")
        stale = await client.call_tool(TOOL, {**arguments, "metadata": {"attributes": {"description": "stale"}}}, raise_on_error=False)
        assert stale.is_error
        for operation in ("ls", "tree"):
            result = await client.call_tool("filesystem_browse", {"operation": operation, "target": {"type": "root"}})
            assert "description=" + json.dumps(description) in result.content[0].text
            assert "\nforged row" not in result.content[0].text
        cleared = await client.call_tool(TOOL, {
            "node_id": node_id, "metadata": {"attributes": {"description": ""}}, "expected_revision": 2,
        })
        assert cleared.structured_content["metadata"]["attributes"] == {"team": "research"}
        assert cleared.structured_content["revision"] == 3
    assert filesystem.content.put_count == 0
    stored = await filesystem.services.browsing().get_node(filesystem.callers.capture(), UUID(node_id))
    assert stored.metadata.attributes == {"team": "research"}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "directory"])
@pytest.mark.parametrize("content_type", ["text/markdown", {}])
async def test_node_update_partial_metadata_preserves_attributes_and_placement(
    filesystem_invocation_mcp: FilesystemMcp, kind: str, content_type: object,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "node", kind)
        initial = await client.call_tool(TOOL, {
            "node_id": node_id, "metadata": {"attributes": {"description": "Read for context", "team": "research"}},
            "expected_revision": 1,
        })
        updated = await client.call_tool(TOOL, {
            "node_id": node_id, "metadata": {"content_type": content_type}, "expected_revision": 2,
        })
        assert updated.structured_content["metadata"] == {
            "attributes": {"description": "Read for context", "team": "research"}, "content_type": content_type,
        }
        for field in ("id", "name", "parent_id", "kind", "created_at"):
            assert updated.structured_content[field] == initial.structured_content[field]
        assert updated.structured_content["revision"] == 3
        attributes_only = await client.call_tool(TOOL, {
            "node_id": node_id, "metadata": {"attributes": {"tag": "release"}}, "expected_revision": 3,
        })
        assert attributes_only.structured_content["metadata"] == {
            "attributes": {"description": "Read for context", "team": "research", "tag": "release"},
            "content_type": content_type,
        }
        assert attributes_only.structured_content["revision"] == 4
    assert filesystem_invocation_mcp.content.put_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {"description": "legacy", "expected_revision": 1},
    {"metadata": None, "expected_revision": 1},
    {"metadata": {}, "expected_revision": 1},
    {"metadata": {"attributes": {}}, "expected_revision": 1},
    {"metadata": {"attributes": None}, "expected_revision": 1},
    {"metadata": {"content_type": None}, "expected_revision": 1},
    {"metadata": {"attributes": {"description": 3}}, "expected_revision": 1},
    {"metadata": {"extra": "unsupported"}, "expected_revision": 1},
    {"metadata": {"attributes": {"description": "x"}}, "expected_revision": 0},
    {"metadata": {"attributes": {"description": "x"}}, "expected_revision": True},
    {"metadata": {"attributes": {"description": "x"}}, "expected_revision": 10_000_000_000_000_000_000},
    {"metadata": {"attributes": {"description": "x"}}},
    {"metadata": {"attributes": {"description": "x"}}, "name": {}, "expected_revision": 1},
    {"metadata": {"attributes": {"description": "x"}}, "parent_id": {}, "expected_revision": 1},
])
async def test_node_update_rejects_invalid_metadata_and_structural_values(
    filesystem_invocation_mcp: FilesystemMcp, arguments: dict[str, object],
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "node", "file")
        result = await client.call_tool(TOOL, {"node_id": node_id, **arguments}, raise_on_error=False)
    assert result.is_error
    stored = await filesystem_invocation_mcp.services.browsing().get_node(
        filesystem_invocation_mcp.callers.capture(), UUID(node_id),
    )
    assert stored.revision == 1
    assert stored.metadata.attributes == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "directory"])
@pytest.mark.parametrize("permissions,visible", [
    ({Permission.DISCOVER, Permission.WRITE}, True),
    ({Permission.WRITE}, False),
    ({Permission.DISCOVER}, False),
    ({Permission.DISCOVER, Permission.READ}, False),
])
async def test_node_update_visibility_uses_same_node_discover_and_write(
    filesystem_mcp: FilesystemMcp, kind: str, permissions: set[Permission], visible: bool,
) -> None:
    node_id = await private_node(filesystem_mcp, kind)
    await grant(filesystem_mcp, node_id, "bob", permissions)
    await filesystem_mcp.runtime.reconcile()
    select_caller(filesystem_mcp, "bob")
    assert (TOOL in await listed_tools(filesystem_mcp)) == visible
    if visible:
        async with Client(filesystem_mcp.server) as client:
            result = await client.call_tool(TOOL, {
                "node_id": str(node_id), "metadata": {"attributes": {"description": "direct"}}, "expected_revision": 1,
            })
        assert result.structured_content["metadata"]["attributes"]["description"] == "direct"



@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "directory"])
async def test_combined_rename_move_metadata_and_stale_request(
    filesystem_invocation_mcp: FilesystemMcp, kind: str,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        root = await root_id(client)
        destination = await create_node(client, root, "destination", "directory")
        node_id = await create_node(client, root, "node", kind)
        arguments = {
            "node_id": node_id, "expected_revision": 1,
            "name": "renamed", "parent_id": destination,
            "metadata": {"attributes": {"description": "Read first"}},
        }
        result = await client.call_tool(TOOL, arguments)
        updated = result.structured_content
        assert (updated["name"], updated["parent_id"], updated["revision"]) == ("renamed", destination, 2)
        assert updated["metadata"]["attributes"] == {"description": "Read first"}
        assert any(isinstance(item, ResourceLink) for item in result.content) == (kind == "file")
        stale = await client.call_tool(TOOL, {**arguments, "name": "stale"}, raise_on_error=False)
        assert stale.is_error
        current = await client.call_tool("get_filesystem_node", {"node_id": node_id})
        assert current.structured_content == updated
    assert filesystem_invocation_mcp.content.put_count == 0



@pytest.mark.asyncio
async def test_root_cannot_be_renamed_or_moved(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        root = await root_id(client)
        for patch in ({"name": ""}, {"parent_id": root}):
            result = await client.call_tool(TOOL, {"node_id": root, "expected_revision": 1, **patch}, raise_on_error=False)
            assert result.is_error
        current = await client.call_tool("get_filesystem_node", {"node_id": root})
        assert current.structured_content["revision"] == 1


@pytest.mark.asyncio
async def test_update_returns_committed_access_snapshot_after_writer_grant_revocation(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from umbod.core.filesystem import Principal, PrincipalType
    from umbod.core.filesystem.authorization import VerifiedIdentityResolver
    from umbod.core.filesystem.updates import NodeUpdateService
    from umbod.infrastructure import create_access_control_driver, create_filesystem_transactions
    from tests.support.filesystem.access_snapshots import RevokeAfterCommitTransactions

    filesystem = filesystem_invocation_mcp
    node_id = await private_node(filesystem, "directory")
    await grant(filesystem, node_id, "bob", {Permission.DISCOVER, Permission.WRITE})
    policies = create_access_control_driver(database=filesystem.database)
    transactions = RevokeAfterCommitTransactions(
        create_filesystem_transactions(database=filesystem.database), policies, node_id,
        Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob"),
    )
    updates = NodeUpdateService(VerifiedIdentityResolver(), transactions)
    monkeypatch.setattr(filesystem.services, "updates", lambda: updates)
    select_caller(filesystem, "bob")
    async with Client(filesystem.server) as client:
        result = await client.call_tool(TOOL, {
            "node_id": str(node_id), "expected_revision": 1, "name": "committed",
        })
        assert result.structured_content["name"] == "committed"
        assert result.structured_content["revision"] == 2
        assert result.structured_content["permissions"]["can_write"] is True
        assert result.structured_content["visible_to"] == {"type": "restricted"}
        assert result.structured_content["sharing"] == {"can_share": False}
        denied = await client.call_tool("get_filesystem_node", {"node_id": str(node_id)}, raise_on_error=False)
        assert denied.is_error
