from dataclasses import dataclass
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import (
    AccessGrant,
    ContentRef,
    Node,
    NodeId,
    NodeKind,
    NodeMetadata,
    Ownership,
    Permission,
    PrincipalType,
    RootParent,
    WrongNodeKind,
)
from umbod.core.filesystem.authorization import PermissionDenied, ResolvedIdentity
from umbod.core.filesystem.browsing import BrowsingService, FilesystemBrowsing, NodeSummary
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import create_access_control_driver, create_namespace_driver, create_filesystem_transactions
from tests.support.filesystem.authorization import (
    AuthorizationContext,
    caller,
    create_authorization_context,
    principal,
)


@dataclass(frozen=True)
class BrowsingContext:
    browsing: FilesystemBrowsing
    authorization: AuthorizationContext


@pytest.fixture
def browsing_context(filesystem_runtime: PersistenceRuntime) -> BrowsingContext:
    context = create_authorization_context(
        create_namespace_driver(database=filesystem_runtime.database),
        create_access_control_driver(database=filesystem_runtime.database),
    )
    for name in ("alice", "bob"):
        context.resolver.identities[caller(name)] = ResolvedIdentity(
            user=principal(name, PrincipalType.USER, "provider"), groups=[]
        )
    browsing: FilesystemBrowsing = BrowsingService(
        context.namespace, context.authorization, context.resolver,
        create_filesystem_transactions(database=filesystem_runtime.database),
    )
    return BrowsingContext(browsing, context)


async def set_owner(context: BrowsingContext, node_id: NodeId, name: str) -> None:
    await context.authorization.policies.set_owner(
        Ownership(node_id=node_id, owner=principal(name, PrincipalType.USER, "provider"))
    )


async def grant(
    context: BrowsingContext, node_id: NodeId, permission: Permission
) -> None:
    await context.authorization.policies.add_grant(
        AccessGrant(
            node_id=node_id,
            principal=principal("alice", PrincipalType.USER, "provider"),
            permissions={permission},
            recursive=True,
        )
    )


async def child(
    context: BrowsingContext, parent_id: NodeId, name: str, kind: NodeKind
) -> Node:
    return await context.authorization.namespace.create_node(
        parent_id, name, kind,
        NodeMetadata(content_type="text/plain", attributes={"custom": "visible"}),
    )


@pytest.mark.asyncio
async def test_root_and_direct_lookup_return_complete_safe_summaries(
    browsing_context: BrowsingContext,
) -> None:
    context = browsing_context
    root = await context.authorization.namespace.get_root()
    await set_owner(context, root.id, "alice")
    root_summary = await context.browsing.get_root(caller("alice"))
    assert isinstance(root_summary.parent_id, RootParent)
    assert root_summary == await context.browsing.get_node(caller("alice"), root.id)
    node = await child(context, root.id, "file", NodeKind.FILE)
    node = await context.authorization.namespace.update_node(
        node.id, content=ContentRef(key="secret-key", size=123), expected_revision=1
    )
    await set_owner(context, node.id, "bob")
    await grant(context, node.id, Permission.DISCOVER)
    observed = await context.browsing.get_node(caller("alice"), node.id)
    expected = node.model_dump(exclude={"content"})
    assert observed.model_dump() == expected
    assert set(observed.model_dump()) == {
        "id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision"
    }
    assert "secret-key" not in observed.model_dump_json()
    with pytest.raises(ValidationError):
        observed.name = "changed"
    observed.metadata.attributes["custom"] = "changed"
    assert node.metadata.attributes == {"custom": "visible"}
    assert (await context.browsing.get_node(caller("alice"), node.id)).metadata.attributes == {"custom": "visible"}
    assert (await context.authorization.namespace.get_node(node.id)).metadata.attributes == {"custom": "visible"}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["root", "node", "list"])
@pytest.mark.parametrize("reason", ["read-only", "unowned", "unresolved", "other-owner", "missing"])
async def test_targets_without_discover_are_uniformly_denied(
    browsing_context: BrowsingContext, operation: str, reason: str,
) -> None:
    context = browsing_context
    root = await context.authorization.namespace.get_root()
    node_id = uuid4() if reason == "missing" and operation != "root" else root.id
    if reason != "unowned":
        await set_owner(context, node_id, "bob")
    if reason == "read-only":
        await grant(context, node_id, Permission.READ)
    if reason == "unresolved":
        context.authorization.resolver.identities.clear()
    with pytest.raises(PermissionDenied, match=f"^discover denied for node {node_id}$"):
        if operation == "root":
            await context.browsing.get_root(caller("alice"))
        elif operation == "node":
            await context.browsing.get_node(caller("alice"), node_id)
        else:
            await context.browsing.list_children(caller("alice"), node_id)


@pytest.mark.asyncio
async def test_listing_filters_each_child_preserving_exact_unicode_name_order(
    browsing_context: BrowsingContext,
) -> None:
    context = browsing_context
    root = await context.authorization.namespace.get_root()
    await set_owner(context, root.id, "alice")
    visible: list[Node] = []
    for name in ("é", "z", "a", "é", "A", "hidden", "read-only", "unowned"):
        node = await child(context, root.id, name, NodeKind.FILE)
        if name == "unowned":
            continue
        await set_owner(context, node.id, "bob")
        if name == "hidden":
            continue
        await grant(context, node.id, Permission.READ if name == "read-only" else Permission.DISCOVER)
        if name != "read-only":
            visible.append(node)
    result = await context.browsing.list_children(caller("alice"), root.id)
    assert [item.id for item in result] == [node.id for node in sorted(visible, key=lambda node: node.name)]
    assert [item.name for item in result] == ["A", "a", "é", "z", "é"]
    assert all(isinstance(item, NodeSummary) for item in result)


@pytest.mark.asyncio
async def test_direct_child_discovery_needs_no_parent_authority_but_listing_does(
    browsing_context: BrowsingContext,
) -> None:
    context = browsing_context
    root = await context.authorization.namespace.get_root()
    node = await child(context, root.id, "visible", NodeKind.FILE)
    await set_owner(context, node.id, "alice")
    assert (await context.browsing.get_node(caller("alice"), node.id)).id == node.id
    with pytest.raises(PermissionDenied):
        await context.browsing.list_children(caller("alice"), root.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized", [False, True])
async def test_file_parent_kind_is_checked_only_after_discover(
    browsing_context: BrowsingContext, authorized: bool,
) -> None:
    context = browsing_context
    root = await context.authorization.namespace.get_root()
    node = await child(context, root.id, "file", NodeKind.FILE)
    await set_owner(context, node.id, "alice" if authorized else "bob")
    with pytest.raises(WrongNodeKind if authorized else PermissionDenied):
        await context.browsing.list_children(caller("alice"), node.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden_child", [False, True])
async def test_empty_and_fully_filtered_directories_have_identical_results(
    browsing_context: BrowsingContext, hidden_child: bool,
) -> None:
    context = browsing_context
    root = await context.authorization.namespace.get_root()
    await set_owner(context, root.id, "alice")
    if hidden_child:
        await child(context, root.id, "hidden", NodeKind.DIRECTORY)
    assert list(await context.browsing.list_children(caller("alice"), root.id)) == []


@pytest.mark.asyncio
async def test_repeated_browsing_observes_revocation_and_caller_isolation(
    browsing_context: BrowsingContext,
) -> None:
    context = browsing_context
    root = await context.authorization.namespace.get_root()
    await set_owner(context, root.id, "bob")
    await grant(context, root.id, Permission.DISCOVER)
    node = await child(context, root.id, "file", NodeKind.FILE)
    await set_owner(context, node.id, "alice")
    assert len(await context.browsing.list_children(caller("alice"), root.id)) == 1
    assert list(await context.browsing.list_children(caller("bob"), root.id)) == []
    await set_owner(context, node.id, "bob")
    assert list(await context.browsing.list_children(caller("alice"), root.id)) == []
    await context.authorization.policies.remove_grant(root.id, principal("alice", PrincipalType.USER, "provider"))
    with pytest.raises(PermissionDenied):
        await context.browsing.get_root(caller("alice"))
    with pytest.raises(PermissionDenied):
        await context.browsing.list_children(caller("alice"), root.id)
    assert (await context.browsing.get_node(caller("bob"), node.id)).id == node.id
    context.authorization.resolver.identities.clear()
    with pytest.raises(PermissionDenied):
        await context.browsing.get_node(caller("bob"), node.id)
