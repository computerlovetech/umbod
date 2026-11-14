from uuid import UUID, uuid4

import pytest
from fastmcp import Client
from mcp.shared.exceptions import MCPError

from umbod.core.filesystem import AccessGrant, NodeKind, NodeMetadata, Ownership, Permission, Principal, PrincipalType
from umbod.core.filesystem.models import UnspecifiedContentType
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.infrastructure import create_filesystem_transactions
from umbod.mcp.filesystem.links import file_resource_uri

from .conftest import FilesystemState, create_filesystem_server
from .test_visibility import select_caller


@pytest.mark.asyncio
@pytest.mark.parametrize("node_kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_unmanaged_ownership_and_grants_never_authorize_tools_resources_or_discovery(
    filesystem_state: FilesystemState, node_kind: NodeKind,
) -> None:
    filesystem = create_filesystem_server(filesystem_state, filtered=False)
    principal = Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob")
    async with create_filesystem_transactions(database=filesystem.database).transaction() as session:
        unmanaged = await session.namespace.create_node(
            ROOT_ID, "unmanaged", node_kind, NodeMetadata(content_type=UnspecifiedContentType(), attributes={}),
        )
        for node_id in (ROOT_ID, unmanaged.id):
            await session.access_control.set_owner(Ownership(node_id=node_id, owner=principal))
            await session.access_control.add_grant(AccessGrant(
                node_id=node_id, principal=principal, permissions=set(Permission), recursive=True,
            ))
    select_caller(filesystem, "bob")
    await filesystem.runtime.reconcile()
    async with Client(filesystem.server) as client:
        missing = await client.call_tool("get_filesystem_node", {"node_id": str(uuid4())}, raise_on_error=False)
        for node_id in (ROOT_ID, unmanaged.id):
            denied = await client.call_tool("get_filesystem_node", {"node_id": str(node_id)}, raise_on_error=False)
            assert denied.is_error
            assert denied.content[:1] == missing.content[:1]
            assert denied.meta["computerlove.tech/umbod"]["guidance"] == missing.meta["computerlove.tech/umbod"]["guidance"]
            inspected = await client.call_tool("filesystem_browse", {
                "operation": "stat", "target": {"type": "node", "node_id": str(node_id)},
            }, raise_on_error=False)
            assert inspected.is_error
            changed = await client.call_tool("update_filesystem_node", {
                "node_id": str(node_id), "expected_revision": 1, "name": "inaccessible",
            }, raise_on_error=False)
            assert changed.is_error
            with pytest.raises(MCPError, match="filesystem_permission_denied"):
                await client.read_resource(file_resource_uri(UUID(str(node_id))))
    filtered = create_filesystem_server(filesystem_state, filtered=True)
    async with Client(filtered.server) as client:
        assert {tool.name for tool in await client.list_tools()} == {"filesystem_browse"}
        assert await client.list_resource_templates() == []
