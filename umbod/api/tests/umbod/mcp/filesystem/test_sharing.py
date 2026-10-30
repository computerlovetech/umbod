import json
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastmcp import Client
from jsonschema import ValidationError as SchemaValidationError, validate

from umbod.core.callers import AuthenticationProvenance, CallerSnapshot
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.models import NodeId
from umbod.core.filesystem.sharing import (
    FilesystemSharing, NodeSharingSummaries, RestrictedNodeSharingSummary,
)
from umbod.core.groups import RegisterGroupMetadata, UpdateGroupMetadata
from umbod.core.groups.stores.composition import create_group_management
from umbod.infrastructure import create_access_control_driver

from .conftest import FilesystemMcp, caller_snapshot
from .test_browsing import create_node
from .test_tools import root_id

VARIANTS = ["ls", "tree", "stat", "get_filesystem_root", "get_filesystem_node", "list_filesystem_children"]


def request(variant: str, target: str) -> tuple[str, dict[str, Any]]:
    if variant in {"ls", "tree", "stat"}:
        return "filesystem_browse", {"operation": variant, "target": {"type": "node", "node_id": target}}
    if variant == "get_filesystem_root":
        return variant, {}
    return variant, {"parent_id" if variant == "list_filesystem_children" else "node_id": target}


def returned_nodes(variant: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    if variant == "list_filesystem_children":
        return data["nodes"]
    if variant.startswith("get_"):
        return [data]
    result = data["result"]
    entries = result.get("entries", [])
    return [result["node"], *[entry["node"] if variant == "tree" else entry for entry in entries]]


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", VARIANTS)
async def test_restricted_reads_omit_grants_in_every_read_variant(
    filesystem_mcp: FilesystemMcp, variant: str,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        child = await create_node(client, root, "visible", "file")
        await create_access_control_driver(database=filesystem_mcp.database).add_grant(AccessGrant(
            node_id=UUID(child), principal=Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob"),
            permissions={Permission.DISCOVER}, recursive=False,
        ))
        filesystem_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        tool, arguments = request(variant, root)
        result = await client.call_tool(tool, arguments)
        descriptor = next(item for item in await client.list_tools() if item.name == tool)
    validate(result.structured_content, descriptor.output_schema)
    assert all(node["sharing"] == {"can_share": False} for node in returned_nodes(variant, result.structured_content))


class RecordingSharing:
    def __init__(self, delegate: FilesystemSharing) -> None:
        self.delegate = delegate
        self.calls: list[tuple[CallerSnapshot, tuple[NodeId, ...]]] = []

    async def summarize_nodes(self, snapshot: CallerSnapshot, node_ids: tuple[NodeId, ...]) -> NodeSharingSummaries:
        self.calls.append((snapshot, node_ids))
        return await self.delegate.summarize_nodes(snapshot, node_ids)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", VARIANTS)
async def test_all_read_variants_advertise_and_return_required_sharing(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, variant: str,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        owned = await create_node(client, root, "owned", "directory")
        await create_node(client, owned, "child", "file")
        recorder = RecordingSharing(filesystem_mcp.services.sharing())
        monkeypatch.setattr(filesystem_mcp.services, "sharing", lambda: recorder)
        captures = filesystem_mcp.callers.count
        tool, arguments = request(variant, root if variant == "get_filesystem_root" else owned)
        result = await client.call_tool(tool, arguments)
        descriptor = next(item for item in await client.list_tools() if item.name == tool)
    validate(result.structured_content, descriptor.output_schema)
    nodes = returned_nodes(variant, result.structured_content)
    incomplete = deepcopy(result.structured_content)
    returned_nodes(variant, incomplete)[0].pop("sharing")
    with pytest.raises(SchemaValidationError):
        validate(incomplete, descriptor.output_schema)
    invalid_restricted = deepcopy(result.structured_content)
    returned_nodes(variant, invalid_restricted)[0]["sharing"] = {"can_share": False, "grants": []}
    with pytest.raises(SchemaValidationError):
        validate(invalid_restricted, descriptor.output_schema)
    for node in nodes:
        assert node["sharing"] == ({"can_share": False} if node["id"] == root else {"can_share": True, "grants": []})
    assert filesystem_mcp.callers.count == captures + 1
    assert recorder.calls == [(filesystem_mcp.callers.current.get(), tuple(UUID(node["id"]) for node in nodes))]
    if variant in {"ls", "tree", "stat"}:
        assert "no manageable direct grants" in result.content[0].text
        assert "sharing" not in result.structured_content["result"]["breadcrumbs"]


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["ls", "tree"])
async def test_sharing_batch_contains_only_returned_nodes_after_limits_and_visibility(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, variant: str,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        first = await create_node(client, root, "a", "directory")
        await create_node(client, first, "beyond-depth", "file")
        await create_node(client, root, "limited-away", "file")
        filesystem_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        await create_node(client, root, "hidden", "file")
        filesystem_mcp.callers.current.set(caller_snapshot(
            "alice", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        recorder = RecordingSharing(filesystem_mcp.services.sharing())
        monkeypatch.setattr(filesystem_mcp.services, "sharing", lambda: recorder)
        tool, arguments = request(variant, root)
        arguments["max_entries"] = 1
        if variant == "tree":
            arguments["depth"] = 1
        captures = filesystem_mcp.callers.count
        result = await client.call_tool(tool, arguments)
    assert filesystem_mcp.callers.count == captures + 1
    assert recorder.calls == [(filesystem_mcp.callers.current.get(), (UUID(root), UUID(first)))]
    assert [node["sharing"] for node in returned_nodes(variant, result.structured_content)] == [
        {"can_share": False}, {"can_share": True, "grants": []},
    ]
    assert "sharing unavailable (not permitted)" in result.content[0].text
    assert "no manageable direct grants" in result.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", VARIANTS)
async def test_read_sharing_projects_current_exact_recipients_and_protects_other_grants(
    filesystem_mcp: FilesystemMcp, variant: str,
) -> None:
    identifier = ' Team/"\n '
    label = 'Current "label"\nnext'
    groups = create_group_management(database=filesystem_mcp.database)
    await groups.register_group_metadata(RegisterGroupMetadata(group_id=identifier, label="Old", description="hidden"))
    await groups.update_group_metadata(identifier, UpdateGroupMetadata(label=label, description="hidden", expected_revision=1))
    policies = create_access_control_driver(database=filesystem_mcp.database)
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        owned = await create_node(client, root, "owned", "directory")
        target = root if variant == "get_filesystem_root" else owned
        if variant == "list_filesystem_children":
            target_node = await create_node(client, owned, "child", "file")
        else:
            target_node = target
        if target_node == root:
            await policies.add_grant(AccessGrant(
                node_id=UUID(root), principal=Principal(type=PrincipalType.USER, issuer="https://issuer", id="alice"),
                permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False,
            ))
        for issuer, recursive in [("https://issuer", False), ("foreign", False)]:
            await policies.add_grant(AccessGrant(
                node_id=UUID(target_node), principal=Principal(type=PrincipalType.GROUP, issuer=issuer, id=identifier),
                permissions={Permission.READ, Permission.DISCOVER}, recursive=recursive,
            ))
        await policies.add_grant(AccessGrant(
            node_id=UUID(target_node), principal=Principal(type=PrincipalType.GROUP, issuer="https://issuer", id="recursive"),
            permissions={Permission.READ}, recursive=True,
        ))
        tool, arguments = request(variant, target)
        result = await client.call_tool(tool, arguments)
    nodes = returned_nodes(variant, result.structured_content)
    node = next(node for node in nodes if node["id"] == target_node)
    expected_grants = [{
        "recipient": {"type": "group", "group_id": identifier, "label": label},
        "permissions": ["discover", "read"],
    }]
    if target_node == root:
        expected_grants.append({
            "recipient": {"type": "group", "group_id": "writers", "label": "writers"},
            "permissions": ["discover", "write"],
        })
    assert node["sharing"] == {"can_share": True, "grants": expected_grants}
    if variant in {"ls", "tree", "stat"}:
        text = result.content[0].text
        assert json.dumps(label) in text
        assert json.dumps(identifier) in text
        assert "foreign" not in text
        assert "recursive" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "mismatched", "duplicate", "error"])
async def test_incomplete_or_failed_sharing_is_sanitized_not_restricted(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        summary = RestrictedNodeSharingSummary(node_id=UUID(root) if failure == "duplicate" else uuid4(), can_share=False)
        sharing = Mock(spec=FilesystemSharing)
        sharing.summarize_nodes = AsyncMock(
            return_value=NodeSharingSummaries(nodes=() if failure == "missing" else (summary, summary) if failure == "duplicate" else (summary,)),
            side_effect=RuntimeError("secret policy") if failure == "error" else None,
        )
        monkeypatch.setattr(filesystem_mcp.services, "sharing", lambda: sharing)
        result = await client.call_tool("filesystem_browse", {"operation": "stat", "target": {"type": "root"}}, raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == "filesystem_operation_failed: Filesystem operation failed"
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_empty_legacy_children_uses_one_empty_batch(filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        recorder = RecordingSharing(filesystem_mcp.services.sharing())
        monkeypatch.setattr(filesystem_mcp.services, "sharing", lambda: recorder)
        result = await client.call_tool("list_filesystem_children", {"parent_id": root})
    assert result.structured_content == {"nodes": []}
    assert recorder.calls == [(filesystem_mcp.callers.current.get(), ())]


@pytest.mark.asyncio
async def test_legacy_children_deduplicates_batch_in_first_order_and_preserves_node_order(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        root = await root_id(client)
        first = await create_node(client, root, "first", "file")
        second = await create_node(client, root, "second", "file")
        browsing = filesystem_mcp.services.browsing()
        caller = filesystem_mcp.callers.current.get()
        first_node = await browsing.get_node(caller, UUID(first))
        second_node = await browsing.get_node(caller, UUID(second))
        monkeypatch.setattr(browsing, "list_children", AsyncMock(return_value=[first_node, second_node, first_node]))
        monkeypatch.setattr(filesystem_mcp.services, "browsing", lambda: browsing)
        sharing = filesystem_mcp.services.sharing()
        summaries = await sharing.summarize_nodes(caller, (UUID(second), UUID(first)))
        summarize = AsyncMock(return_value=summaries)
        monkeypatch.setattr(sharing, "summarize_nodes", summarize)
        monkeypatch.setattr(filesystem_mcp.services, "sharing", lambda: sharing)
        result = await client.call_tool("list_filesystem_children", {"parent_id": root})
    summarize.assert_awaited_once_with(caller, (UUID(first), UUID(second)))
    assert [node["id"] for node in result.structured_content["nodes"]] == [first, second, first]
    assert all(node["sharing"] == {"can_share": True, "grants": []} for node in result.structured_content["nodes"])
