import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from umbod.core.filesystem import (
    AccessGrant, NamespaceDriver, Node, NodeId, NodeKind, NodeMetadata, Ownership, Permission, PrincipalType,
)
from umbod.core.filesystem.authorization import ResolvedIdentity
from umbod.core.filesystem.browsing import BrowsingService, FilesystemBrowsing
from umbod.core.filesystem.transactions import FilesystemSession, FilesystemTransactions
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    create_access_control_driver, create_filesystem_browsing, create_filesystem_transactions, create_namespace_driver,
)
from tests.support.filesystem.authorization import (
    AuthorizationContext, caller, create_authorization_context, principal,
)


@dataclass(frozen=True)
class BreadcrumbContext:
    browsing: FilesystemBrowsing
    authorization: AuthorizationContext


@pytest.fixture
def breadcrumbs(filesystem_runtime: PersistenceRuntime) -> BreadcrumbContext:
    context = create_authorization_context(
        create_namespace_driver(database=filesystem_runtime.database),
        create_access_control_driver(database=filesystem_runtime.database),
    )
    context.resolver.identities[caller("alice")] = ResolvedIdentity(
        user=principal("alice", PrincipalType.USER, "issuer"),
        groups=[principal("team", PrincipalType.GROUP, "issuer")],
    )
    return BreadcrumbContext(
        create_filesystem_browsing(database=filesystem_runtime.database, resolver=context.resolver), context,
    )


async def own(context: BreadcrumbContext, node_id: NodeId, owner: str) -> None:
    await context.authorization.policies.set_owner(Ownership(
        node_id=node_id, owner=principal(owner, PrincipalType.USER, "issuer"),
    ))


async def path(context: BreadcrumbContext, kind: NodeKind) -> list[Node]:
    root = await context.authorization.namespace.get_root()
    nodes = [root]
    for name, node_kind in (("first", NodeKind.DIRECTORY), ("second", NodeKind.DIRECTORY), ("target", kind)):
        node = await context.authorization.namespace.create_node(
            nodes[-1].id, name, node_kind,
            NodeMetadata(content_type="text/plain", attributes={"secret": "not breadcrumbs"}),
        )
        nodes.append(node)
    for node in nodes:
        await own(context, node.id, "alice")
    return nodes


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [NodeKind.DIRECTORY, NodeKind.FILE])
async def test_full_paths_are_ordered_minimal_and_include_target(breadcrumbs: BreadcrumbContext, kind: NodeKind) -> None:
    nodes = await path(breadcrumbs, kind)
    for index, node in enumerate(nodes):
        result = await breadcrumbs.browsing.get_breadcrumbs(caller("alice"), node.id)
        assert result.complete is True
        assert result.model_dump() == {
            "items": [{"id": entry.id, "name": entry.name, "kind": entry.kind} for entry in nodes[:index + 1]],
            "complete": True,
        }
    assert (await breadcrumbs.browsing.get_breadcrumbs(caller("alice"), nodes[0].id)).items[0].name == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden_index", [0, 1, 2])
@pytest.mark.parametrize("reason", ["other-owner", "unowned"])
async def test_first_hidden_ancestor_ends_path_without_skipping_to_visible_grandparents(
    breadcrumbs: BreadcrumbContext, hidden_index: int, reason: str,
) -> None:
    nodes = await path(breadcrumbs, NodeKind.FILE)
    if reason == "unowned":
        await breadcrumbs.authorization.policies.clear_node(nodes[hidden_index].id)
    else:
        await own(breadcrumbs, nodes[hidden_index].id, "bob")
    result = await breadcrumbs.browsing.get_breadcrumbs(caller("alice"), nodes[-1].id)
    assert result.complete is False
    assert [item.id for item in result.items] == [node.id for node in nodes[hidden_index + 1:]]
    assert str(nodes[hidden_index].id) not in result.model_dump_json()
    if hidden_index:
        assert nodes[hidden_index].name not in result.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["missing", "hidden", "unowned", "read-only", "unresolved"])
async def test_target_denial_is_indistinguishable(breadcrumbs: BreadcrumbContext, reason: str) -> None:
    node = (await path(breadcrumbs, NodeKind.FILE))[-1]
    if reason in ("hidden", "read-only"):
        await own(breadcrumbs, node.id, "bob")
    if reason == "read-only":
        await breadcrumbs.authorization.policies.add_grant(AccessGrant(
            node_id=node.id, principal=principal("alice", PrincipalType.USER, "issuer"),
            permissions={Permission.READ}, recursive=False,
        ))
    if reason == "unowned":
        await breadcrumbs.authorization.policies.clear_node(node.id)
    if reason == "unresolved":
        breadcrumbs.authorization.resolver.identities.clear()
    node_id = uuid4() if reason == "missing" else node.id
    with pytest.raises(PermissionDenied, match=f"^discover denied for node {node_id}$"):
        await breadcrumbs.browsing.get_breadcrumbs(caller("alice"), node_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("principal_type,issuer,identifier,allowed", [
    (PrincipalType.USER, "issuer", "alice", True),
    (PrincipalType.GROUP, "issuer", "team", True),
    (PrincipalType.USER, "other", "alice", False),
    (PrincipalType.GROUP, "other", "team", False),
    (PrincipalType.USER, "issuer", "bob", False),
])
async def test_exact_issuer_user_and_group_grants_and_revocation(
    breadcrumbs: BreadcrumbContext, principal_type: PrincipalType, issuer: str, identifier: str, allowed: bool,
) -> None:
    nodes = await path(breadcrumbs, NodeKind.FILE)
    target = nodes[-1]
    await own(breadcrumbs, target.id, "bob")
    recipient = principal(identifier, principal_type, issuer)
    grant = AccessGrant(node_id=target.id, principal=recipient, permissions={Permission.DISCOVER}, recursive=True)
    await breadcrumbs.authorization.policies.add_grant(grant)
    if allowed:
        assert (await breadcrumbs.browsing.get_breadcrumbs(caller("alice"), target.id)).complete
        await breadcrumbs.authorization.policies.remove_grant(target.id, recipient)
    with pytest.raises(PermissionDenied):
        await breadcrumbs.browsing.get_breadcrumbs(caller("alice"), target.id)


@pytest.mark.asyncio
async def test_recursive_ancestor_grant_does_not_authorize_target(breadcrumbs: BreadcrumbContext) -> None:
    nodes = await path(breadcrumbs, NodeKind.FILE)
    await own(breadcrumbs, nodes[-1].id, "bob")
    await breadcrumbs.authorization.policies.add_grant(AccessGrant(
        node_id=nodes[-2].id, principal=principal("alice", PrincipalType.USER, "issuer"),
        permissions={Permission.DISCOVER}, recursive=True,
    ))
    with pytest.raises(PermissionDenied):
        await breadcrumbs.browsing.get_breadcrumbs(caller("alice"), nodes[-1].id)


class GatedBreadcrumbTransactions:
    def __init__(self, transactions: FilesystemTransactions, checked: asyncio.Event, release: asyncio.Event) -> None:
        self._transactions = transactions
        self._checked = checked
        self._release = release

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            namespace = create_autospec(NamespaceDriver, instance=True)
            reads = 0

            async def get_node(node_id: NodeId) -> Node:
                nonlocal reads
                reads += 1
                if reads == 2:
                    self._checked.set()
                    await self._release.wait()
                return await session.namespace.get_node(node_id)

            namespace.get_node.side_effect = get_node
            yield FilesystemSession(namespace, session.access_control)


@pytest.mark.asyncio
async def test_ancestry_read_serializes_policy_revocation(
    breadcrumbs: BreadcrumbContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    nodes = await path(breadcrumbs, NodeKind.FILE)
    checked, release, revoking = asyncio.Event(), asyncio.Event(), asyncio.Event()
    context = breadcrumbs.authorization
    browsing = BrowsingService(
        context.namespace, context.authorization, context.resolver,
        GatedBreadcrumbTransactions(create_filesystem_transactions(database=filesystem_runtime.database), checked, release),
    )

    async def revoke() -> None:
        revoking.set()
        await own(breadcrumbs, nodes[1].id, "bob")

    pending = asyncio.create_task(browsing.get_breadcrumbs(caller("alice"), nodes[-1].id))
    try:
        await asyncio.wait_for(checked.wait(), timeout=5)
        revocation = asyncio.create_task(revoke())
        await asyncio.wait_for(revoking.wait(), timeout=5)
        assert not revocation.done()
    finally:
        release.set()
    assert (await pending).complete is True
    await revocation
    result = await breadcrumbs.browsing.get_breadcrumbs(caller("alice"), nodes[-1].id)
    assert result.complete is False
    assert [item.id for item in result.items] == [node.id for node in nodes[2:]]
