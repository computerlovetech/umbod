from uuid import uuid4

import pytest

from umbod.core.filesystem import AccessGrant, NodeKind, Ownership, Permission, PrincipalType
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.browsing.exploration import BrowseScope, ScopedBrowsingExplorer
from umbod.core.filesystem.errors import StorageFailure
from umbod.core.filesystem.namespace import ROOT_ID, initial_root
from tests.support.filesystem.authorization import caller, principal
from tests.support.filesystem.exploration import CountingIdentityResolver, MemoryScopeReader, child, scope_for


@pytest.mark.asyncio
async def test_scoped_browse_reuses_sorted_complete_listing_and_resolves_identity_once() -> None:
    root = initial_root()
    nodes = [child(root.id, name, kind) for name, kind in [
        ("z", NodeKind.FILE), ("a", NodeKind.DIRECTORY), ("A", NodeKind.FILE), ("a", NodeKind.FILE),
    ]]
    reader = MemoryScopeReader(scope_for([root, *nodes], [root, *nodes], []))
    resolver = CountingIdentityResolver(True)
    result = await ScopedBrowsingExplorer(reader, resolver, True).browse_node(caller("alice"), root.id)
    assert [node.name for node in result.entries] == ["a", "A", "a", "z"]
    assert result.truncated is False
    assert result.breadcrumbs.complete is True
    root_capability = result.capabilities[0]
    assert root_capability.rename is root_capability.move is root_capability.delete is False
    assert root_capability.edit_description is root_capability.upload is root_capability.create_directory is True
    assert resolver.calls == reader.reads == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("parent_visible", [False, True])
@pytest.mark.parametrize("sharing_available", [False, True])
async def test_direct_file_access_keeps_partial_ancestry_and_does_not_require_parent_write(
    parent_visible: bool, sharing_available: bool,
) -> None:
    root = initial_root()
    parent = child(root.id, "secret", NodeKind.DIRECTORY)
    target = child(parent.id, "target", NodeKind.FILE)
    owned = [target]
    grants = [AccessGrant(
        node_id=parent.id, principal=principal("alice", PrincipalType.USER, "issuer"),
        permissions={Permission.DISCOVER}, recursive=False,
    )] if parent_visible else []
    scope = scope_for([root, parent, target], owned, grants)
    if parent_visible:
        scope = scope.model_copy(update={"ownerships": (*scope.ownerships, Ownership(
            node_id=parent.id, owner=principal("bob", PrincipalType.USER, "issuer"),
        ))})
    result = await ScopedBrowsingExplorer(MemoryScopeReader(scope), CountingIdentityResolver(True), sharing_available).browse_node(caller("alice"), target.id)
    assert result.entries == []
    assert result.breadcrumbs.complete is False
    assert [item.id for item in result.breadcrumbs.items] == ([parent.id, target.id] if parent_visible else [target.id])
    capabilities = result.capabilities[0]
    assert capabilities.rename is capabilities.edit_description is capabilities.delete is True
    assert capabilities.move is capabilities.upload is capabilities.create_directory is False
    assert capabilities.share is sharing_available


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["missing", "unowned", "wrong-issuer", "no-discover", "unresolved"])
async def test_scoped_browse_fails_closed_without_disclosing_target(reason: str) -> None:
    root = initial_root()
    target = child(root.id, "target", NodeKind.FILE)
    recipient = principal("alice", PrincipalType.USER, "other" if reason == "wrong-issuer" else "issuer")
    grant = AccessGrant(
        node_id=target.id,
        principal=recipient, permissions={Permission.WRITE} if reason == "no-discover" else set(Permission),
        recursive=True,
    )
    scope = BrowseScope(
        nodes=(root, target), grants=(grant,),
        ownerships=() if reason == "unowned" else (Ownership(
            node_id=target.id, owner=principal("bob", PrincipalType.USER, "issuer"),
        ),),
    )
    service = ScopedBrowsingExplorer(MemoryScopeReader(scope), CountingIdentityResolver(reason != "unresolved"), True)
    with pytest.raises(PermissionDenied):
        await service.browse_node(caller("alice"), uuid4() if reason == "missing" else target.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["cycle", "file-parent", "invalid-root"])
async def test_discoverable_invalid_ancestry_is_rejected(corruption: str) -> None:
    root = initial_root()
    parent = child(root.id, "parent", NodeKind.DIRECTORY)
    target = child(parent.id, "target", NodeKind.FILE)
    if corruption == "cycle":
        parent = parent.model_copy(update={"parent_id": target.id})
    elif corruption == "file-parent":
        parent = parent.model_copy(update={"kind": NodeKind.FILE})
    else:
        root = root.model_copy(update={"name": "invalid"})
    nodes = [root, parent, target]
    service = ScopedBrowsingExplorer(MemoryScopeReader(scope_for(nodes, nodes, [])), CountingIdentityResolver(True), True)
    with pytest.raises(StorageFailure if corruption == "invalid-root" else PermissionDenied):
        await service.browse_node(caller("alice"), target.id)


@pytest.mark.asyncio
async def test_missing_owner_hides_child_even_with_matching_grants() -> None:
    root = initial_root()
    hidden = child(ROOT_ID, "hidden", NodeKind.FILE)
    scope = scope_for([root, hidden], [root], [AccessGrant(
        node_id=hidden.id, principal=principal("alice", PrincipalType.USER, "issuer"),
        permissions=set(Permission), recursive=False,
    )])
    result = await ScopedBrowsingExplorer(MemoryScopeReader(scope), CountingIdentityResolver(True), True).browse_node(caller("alice"), ROOT_ID)
    assert result.entries == []
    assert [capability.node_id for capability in result.capabilities] == [ROOT_ID]


@pytest.mark.asyncio
@pytest.mark.parametrize("permission", [Permission.READ, Permission.WRITE, Permission.DELETE, Permission.SHARE])
@pytest.mark.parametrize("kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_capabilities_follow_independent_direct_grants(permission: Permission, kind: NodeKind) -> None:
    root = initial_root()
    target = child(root.id, "target", kind)
    scope = BrowseScope(
        nodes=(root, target),
        ownerships=(Ownership(node_id=target.id, owner=principal("bob", PrincipalType.USER, "issuer")),),
        grants=(AccessGrant(
            node_id=target.id, principal=principal("alice", PrincipalType.USER, "issuer"),
            permissions={Permission.DISCOVER, permission}, recursive=False,
        ),),
    )
    result = await ScopedBrowsingExplorer(MemoryScopeReader(scope), CountingIdentityResolver(True), True).browse_node(caller("alice"), target.id)
    capability = result.capabilities[0]
    assert capability.edit_description == (permission == Permission.WRITE)
    assert capability.rename == (permission == Permission.WRITE)
    assert capability.move is False
    assert capability.delete == (kind == NodeKind.FILE and permission == Permission.DELETE)
    assert capability.share == (permission == Permission.SHARE)
    assert capability.upload == capability.create_directory == (kind == NodeKind.DIRECTORY and permission == Permission.WRITE)
