import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastmcp import Client
from jsonschema import ValidationError, validate

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.namespaces import CreateSharedNamespace, NamespaceGroupAccess, SaveSharedNamespace
from umbod.core.groups import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.infrastructure import create_filesystem_namespace_management

from .conftest import FilesystemMcp, caller_snapshot
from .test_browsing import create_node
from .test_tools import METADATA
from .test_visibility import select_caller


@pytest.mark.asyncio
async def test_namespace_listing_provisions_one_private_namespace_and_publishes_its_schema(
    filesystem_mcp: FilesystemMcp,
) -> None:
    select_caller(filesystem_mcp, "new-user")
    async with Client(filesystem_mcp.server) as client:
        descriptor = next(tool for tool in await client.list_tools() if tool.name == "filesystem_browse")
        branch = next(
            value for value in descriptor.input_schema["oneOf"]
            if value["properties"]["operation"]["const"] == "namespaces"
        )
        validate({"operation": "namespaces"}, branch)
        with pytest.raises(ValidationError):
            validate({"operation": "namespaces", "target": {"type": "root"}}, branch)
        result = await client.call_tool("filesystem_browse", {"operation": "namespaces"})
        repeated = await client.call_tool("filesystem_browse", {"operation": "namespaces"})
    validate(result.structured_content, descriptor.output_schema)
    assert result.structured_content == repeated.structured_content
    namespaces = result.structured_content["result"]["namespaces"]
    assert len(namespaces) == 1
    namespace = namespaces[0]
    assert set(namespace) == {"id", "root_node_id", "name", "kind", "permissions", "description"}
    assert namespace["kind"] == "personal"
    assert UUID(namespace["root_node_id"]) != ROOT_ID
    assert namespace["permissions"] == ["delete", "discover", "read", "write"]
    assert namespace["root_node_id"] in result.content[0].text
    assert json.dumps(namespace["name"]) in result.content[0].text


@pytest.mark.asyncio
async def test_root_and_absolute_path_targets_resolve_inside_personal_namespace(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        home = await client.call_tool("filesystem_browse", {"operation": "home"})
        personal_root = home.structured_content["result"]["node"]["id"]
        child = await create_node(client, personal_root, "personal.txt", "file")
        listing = await client.call_tool("filesystem_browse", {"operation": "ls", "target": {"type": "root"}})
        inspected = await client.call_tool("filesystem_browse", {
            "operation": "stat", "target": {"type": "path", "path": "/personal.txt"},
        })
    assert listing.structured_content["result"]["node"]["id"] == personal_root
    assert listing.structured_content["result"]["breadcrumbs"]["complete"] is True
    assert [node["id"] for node in listing.structured_content["result"]["entries"]] == [child]
    assert inspected.structured_content["result"]["node"]["id"] == child
    assert all(
        item["id"] != str(ROOT_ID)
        for item in inspected.structured_content["result"]["breadcrumbs"]["items"]
    )


@pytest.mark.asyncio
async def test_namespaces_isolate_equal_subjects_at_different_issuers(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    filesystem = filesystem_invocation_mcp
    async with Client(filesystem.server) as client:
        first = await client.call_tool("filesystem_browse", {"operation": "namespaces"})
        first_root = first.structured_content["result"]["namespaces"][0]["root_node_id"]
        filesystem.callers.current.set(caller_snapshot(
            "alice", "https://other-issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        other = await client.call_tool("filesystem_browse", {"operation": "namespaces"})
        denied = await client.call_tool("get_filesystem_node", {"node_id": first_root}, raise_on_error=False)
        missing = await client.call_tool("get_filesystem_node", {"node_id": str(uuid4())}, raise_on_error=False)
    assert other.structured_content["result"]["namespaces"][0]["root_node_id"] != first_root
    assert denied.is_error and missing.is_error
    assert denied.content[:1] == missing.content[:1]


@pytest.mark.asyncio
async def test_namespace_revocation_removes_outsider_access_without_removing_creator_authority(
    filesystem_invocation_mcp: FilesystemMcp,
) -> None:
    filesystem = filesystem_invocation_mcp
    await create_group_management(filesystem.database).register_group(RegisterGroup(group_id="writers"))
    management = create_filesystem_namespace_management(database=filesystem.database, issuer="https://issuer")
    shared = await management.create(CreateSharedNamespace(
        name="Shared reference", description='Équipe "shared"\nreference', groups=[NamespaceGroupAccess(group_id="writers", access="read_write")],
    ))
    async with Client(filesystem.server) as client:
        listed = await client.call_tool("filesystem_browse", {"operation": "namespaces"})
        assert any(
            value["id"] == str(shared.id) and value["kind"] == "shared"
            for value in listed.structured_content["result"]["namespaces"]
        )
        namespace = next(value for value in listed.structured_content["result"]["namespaces"] if value["id"] == str(shared.id))
        assert namespace["description"] == shared.description
        assert f"description={json.dumps(shared.description, ensure_ascii=False)}" in listed.content[0].text
        inspected_root = await client.call_tool("filesystem_browse", {"operation": "stat", "target": {"type": "node", "node_id": str(shared.root_node_id)}})
        assert inspected_root.structured_content["result"]["node"]["metadata"]["attributes"]["description"] == shared.description
        created = await client.call_tool("create_filesystem_file", {
            "parent_id": str(shared.root_node_id), "name": "reference.txt", "metadata": METADATA,
        })
        node_id = created.structured_content["id"]
        select_caller(filesystem, "bob", ("writers",))
        assert set(created.structured_content["permissions"]) == {"can_discover", "can_read", "can_write", "can_delete", "can_share"}
        read_only = await management.save(shared.id, SaveSharedNamespace(
            expected_revision=shared.revision, name=shared.name,
            groups=[NamespaceGroupAccess(group_id="writers", access="read")],
        ))
        inspected = await client.call_tool("get_filesystem_node", {"node_id": node_id})
        assert inspected.structured_content["permissions"]["can_write"] is False
        denied_write = await client.call_tool("update_filesystem_node", {
            "node_id": node_id, "expected_revision": 1, "name": "changed.txt",
        }, raise_on_error=False)
        assert denied_write.is_error
        await management.save(shared.id, SaveSharedNamespace(
            expected_revision=read_only.revision, name=read_only.name, groups=[],
        ))
        denied_read = await client.call_tool("get_filesystem_node", {"node_id": node_id}, raise_on_error=False)
        visible = await client.call_tool("filesystem_browse", {"operation": "namespaces"})
    assert denied_read.is_error
    select_caller(filesystem, "alice", ("writers",))
    async with Client(filesystem.server) as client:
        owner = await client.call_tool("get_filesystem_node", {"node_id": node_id})
    assert owner.structured_content["permissions"]["can_share"] is True
    assert owner.structured_content["permissions"]["can_write"] is True
    assert all(value["id"] != str(shared.id) for value in visible.structured_content["result"]["namespaces"])


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{"target": {"type": "root"}}, {"user": "other"}, {"issuer": "other"}])
async def test_namespace_listing_rejects_client_authority_before_caller_capture(
    filesystem_invocation_mcp: FilesystemMcp, extra: dict[str, Any],
) -> None:
    captures = filesystem_invocation_mcp.callers.count
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool("filesystem_browse", {"operation": "namespaces", **extra}, raise_on_error=False)
    assert result.is_error
    assert filesystem_invocation_mcp.callers.count == captures


@pytest.mark.asyncio
@pytest.mark.parametrize("remove", ["direct", "namespace"])
async def test_namespace_baseline_and_direct_item_grants_remain_independent(
    filesystem_invocation_mcp: FilesystemMcp, remove: str,
) -> None:
    from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
    from umbod.infrastructure import create_access_control_driver
    from .test_visibility import shared_namespace, save_namespace_access

    filesystem = filesystem_invocation_mcp
    policy = await shared_namespace(filesystem)
    select_caller(filesystem, "alice", (policy.groups[0].group_id,))
    async with Client(filesystem.server) as client:
        node_id = await create_node(client, str(policy.root_node_id), "reference", "file")
        principal = Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob")
        grants = create_access_control_driver(database=filesystem.database)
        await grants.add_grant(AccessGrant(
            node_id=UUID(node_id), principal=principal, permissions={Permission.DISCOVER, Permission.READ}, recursive=False,
        ))
        if remove == "direct":
            await grants.remove_grant(UUID(node_id), principal)
        else:
            await save_namespace_access(filesystem, policy, None)
        select_caller(filesystem, "bob", (policy.groups[0].group_id,))
        inspected = await client.call_tool("get_filesystem_node", {"node_id": node_id})
        catalog = await client.call_tool("filesystem_browse", {"operation": "namespaces"})
    assert inspected.structured_content["permissions"]["can_read"] is True
    assert inspected.structured_content["permissions"]["can_write"] is (remove == "direct")
    assert any(value["id"] == str(policy.id) for value in catalog.structured_content["result"]["namespaces"]) is (remove == "direct")
