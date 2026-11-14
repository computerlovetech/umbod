from uuid import uuid4

import pytest

from umbod.core.filesystem import NodeKind
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.browsing.exploration import BrowseScope, ScopedBrowsingExplorer
from umbod.core.filesystem.namespace import ROOT_ID, initial_root
from tests.support.filesystem.authorization import caller
from tests.support.filesystem.exploration import CountingIdentityResolver, MemoryScopeReader, child, scope_for
from tests.umbod.core.filesystem.test_effective_permissions import policy, principal


@pytest.mark.asyncio
async def test_scoped_listing_reuses_complete_sorted_listing_and_resolves_once() -> None:
    anchor = initial_root()
    root = child(anchor.id, "namespace", NodeKind.DIRECTORY)
    nodes = [child(root.id, name, kind) for name, kind in [
        ("z", NodeKind.FILE), ("a", NodeKind.DIRECTORY), ("A", NodeKind.FILE), ("a", NodeKind.FILE),
    ]]
    reader = MemoryScopeReader(scope_for([anchor, root, *nodes], (policy(root.id),)))
    resolver = CountingIdentityResolver(True)
    result = await ScopedBrowsingExplorer(reader, resolver).browse_node(caller("alice"), root.id)
    assert [node.name for node in result.entries] == ["a", "A", "a", "z"]
    assert not result.truncated
    assert result.breadcrumbs.complete
    assert [node.id for node in result.breadcrumbs.items] == [root.id]
    capabilities = result.capabilities[0]
    assert not capabilities.rename and not capabilities.move and not capabilities.delete
    assert capabilities.edit_description and capabilities.upload and capabilities.create_directory
    assert resolver.calls == reader.reads == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["missing", "unmanaged", "wrong-issuer", "unresolved", "anchor"])
async def test_scoped_browse_fails_closed_without_disclosing_target(reason: str) -> None:
    anchor = initial_root()
    root = child(anchor.id, "namespace", NodeKind.DIRECTORY)
    target = child(root.id, "target", NodeKind.FILE)
    namespace = policy(root.id)
    if reason == "wrong-issuer":
        namespace = namespace.model_copy(update={"owners": frozenset({principal("bob")})})
    scope = BrowseScope(nodes=(anchor, root, target), ownerships=(), grants=(), namespaces=() if reason == "unmanaged" else (namespace,))
    service = ScopedBrowsingExplorer(MemoryScopeReader(scope), CountingIdentityResolver(reason != "unresolved"))
    node_id = uuid4() if reason == "missing" else ROOT_ID if reason == "anchor" else target.id
    with pytest.raises(PermissionDenied):
        await service.browse_node(caller("alice"), node_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["cycle", "file-parent", "invalid-root"])
async def test_registered_namespace_still_requires_complete_valid_ancestry(corruption: str) -> None:
    anchor = initial_root()
    root = child(anchor.id, "namespace", NodeKind.DIRECTORY)
    target = child(root.id, "target", NodeKind.FILE)
    if corruption == "cycle":
        root = root.model_copy(update={"parent_id": target.id})
    elif corruption == "file-parent":
        root = root.model_copy(update={"kind": NodeKind.FILE})
    else:
        anchor = anchor.model_copy(update={"kind": NodeKind.FILE})
    scope = scope_for([anchor, root, target], (policy(root.id),))
    with pytest.raises(PermissionDenied):
        await ScopedBrowsingExplorer(MemoryScopeReader(scope), CountingIdentityResolver(True)).browse_node(caller("alice"), target.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(NodeKind))
async def test_capabilities_follow_namespace_authority_without_raw_ownership(kind: NodeKind) -> None:
    anchor = initial_root()
    root = child(anchor.id, "namespace", NodeKind.DIRECTORY)
    target = child(root.id, "target", kind)
    scope = scope_for([anchor, root, target], (policy(root.id),))
    result = await ScopedBrowsingExplorer(MemoryScopeReader(scope), CountingIdentityResolver(True)).browse_node(caller("alice"), target.id)
    capability = result.capabilities[0]
    assert capability.edit_description and capability.rename and capability.move
    assert capability.delete == (kind == NodeKind.FILE)
    assert capability.upload == capability.create_directory == (kind == NodeKind.DIRECTORY)
    assert capability.share
