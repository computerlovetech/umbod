import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from umbod.core.filesystem import (
    AccessControlDriver, AccessGrant, ContentRef, FilesystemSession, FilesystemTransactions,
    MissingNode, NamespaceDriver, NodeId, NodeKind, Ownership, OwnershipNotFound, Permission, Principal,
    PrincipalType, RevisionConflict, StorageFailure, WrongNodeKind,
)
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.deletion import DeletionService, FilesystemDeletion
from umbod.core.filesystem.namespace import ROOT_ID
from tests.umbod.core.filesystem.test_authorized_content import ContentContext, alice, caller, metadata, stream
from tests.umbod.core.filesystem.test_authorized_content import content_context as content_context
from tests.umbod.core.filesystem.test_verified_identity import snapshot


def deletion(context: ContentContext) -> FilesystemDeletion:
    return DeletionService(VerifiedIdentityResolver(), context.transactions)


def bob() -> Principal:
    return Principal(type=PrincipalType.USER, issuer="issuer", id="bob")


@pytest.mark.asyncio
async def test_removal_clears_all_policies_but_retains_bytes_and_releases_name(content_context: ContentContext) -> None:
    context = content_context
    node = await context.service.upload(caller(), ROOT_ID, "file", metadata(), stream(b"bytes"))
    stored = await context.namespace.get_node(node.id)
    assert isinstance(stored.content, ContentRef)
    await context.policies.add_grant(AccessGrant(node_id=node.id, principal=bob(), permissions=set(Permission), recursive=True))
    await deletion(context).delete_file(caller(), node.id, expected_revision=node.revision)
    with pytest.raises(MissingNode):
        await context.namespace.get_node(node.id)
    with pytest.raises(OwnershipNotFound):
        await context.policies.get_owner(node.id)
    assert await context.policies.list_grants(node.id) == []
    assert await context.namespace.list_children(ROOT_ID) == []
    assert b"".join([chunk async for chunk in context.content.get(stored.content.key)]) == b"bytes"
    recreated = await context.creation.create_file(caller(), ROOT_ID, "file", metadata())
    assert recreated.id != node.id
    with pytest.raises(PermissionDenied):
        await deletion(context).delete_file(caller(), node.id, expected_revision=node.revision)


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.DELETE}, {Permission.DISCOVER, Permission.WRITE}, {Permission.DISCOVER, Permission.READ}])
async def test_both_direct_discover_and_delete_are_required(content_context: ContentContext, permissions: set[Permission]) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), ROOT_ID, "file", metadata())
    await context.policies.add_grant(AccessGrant(node_id=node.id, principal=bob(), permissions=permissions, recursive=False))
    for identifier in (node.id, uuid4()):
        with pytest.raises(PermissionDenied):
            await deletion(context).check_delete_eligibility(snapshot("bob", "issuer", ()), identifier)
        with pytest.raises(PermissionDenied):
            await deletion(context).delete_file(snapshot("bob", "issuer", ()), identifier, expected_revision=999)
    assert (await context.namespace.get_node(node.id)).revision == node.revision


@pytest.mark.asyncio
@pytest.mark.parametrize("group", [False, True])
async def test_direct_grants_allow_delete_without_parent_write_and_revocation_is_rechecked(content_context: ContentContext, group: bool) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), ROOT_ID, "file", metadata())
    principal = Principal(type=PrincipalType.GROUP, issuer="issuer", id="team") if group else bob()
    actor = snapshot("bob", "issuer", ("team",) if group else ())
    grant = AccessGrant(node_id=node.id, principal=principal, permissions={Permission.DISCOVER, Permission.DELETE}, recursive=False)
    await context.policies.add_grant(grant)
    await deletion(context).check_delete_eligibility(actor, node.id)
    assert await context.namespace.get_node(node.id)
    await context.policies.remove_grant(node.id, principal)
    with pytest.raises(PermissionDenied):
        await deletion(context).delete_file(actor, node.id, expected_revision=node.revision)
    await context.policies.add_grant(grant)
    await deletion(context).delete_file(actor, node.id, expected_revision=node.revision)
    with pytest.raises(MissingNode):
        await context.namespace.get_node(node.id)


@pytest.mark.asyncio
async def test_parent_recursive_grant_and_foreign_issuer_do_not_authorize(content_context: ContentContext) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), ROOT_ID, "file", metadata())
    await context.policies.add_grant(AccessGrant(node_id=ROOT_ID, principal=bob(), permissions=set(Permission), recursive=True))
    await context.policies.add_grant(AccessGrant(node_id=node.id, principal=Principal(type=PrincipalType.USER, issuer="other", id="bob"), permissions=set(Permission), recursive=True))
    with pytest.raises(PermissionDenied):
        await deletion(context).delete_file(snapshot("bob", "issuer", ()), node.id, expected_revision=node.revision)


@pytest.mark.asyncio
async def test_unowned_node_and_unresolved_identity_fail_closed(content_context: ContentContext) -> None:
    context = content_context
    node = await context.namespace.create_node(ROOT_ID, "unowned", NodeKind.FILE, metadata())
    await context.policies.add_grant(AccessGrant(node_id=node.id, principal=alice(), permissions=set(Permission), recursive=False))
    with pytest.raises(PermissionDenied):
        await deletion(context).check_delete_eligibility(caller(), node.id)
    with pytest.raises(PermissionDenied):
        await deletion(context).delete_file(snapshot("alice", "issuer", ("",)), node.id, expected_revision=node.revision)


@pytest.mark.asyncio
async def test_stale_authorized_revision_preserves_node_and_policies(content_context: ContentContext) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), ROOT_ID, "file", metadata())
    owner = await context.policies.get_owner(node.id)
    with pytest.raises(RevisionConflict):
        await deletion(context).delete_file(caller(), node.id, expected_revision=node.revision + 1)
    assert await context.namespace.get_node(node.id)
    assert await context.policies.get_owner(node.id) == owner


@pytest.mark.asyncio
@pytest.mark.parametrize("root", [False, True])
async def test_authorized_directories_and_root_cannot_be_removed(content_context: ContentContext, root: bool) -> None:
    context = content_context
    if root:
        await context.policies.set_owner(Ownership(node_id=ROOT_ID, owner=alice()))
        node = await context.namespace.get_root()
    else:
        node = await context.creation.create_directory(caller(), ROOT_ID, "folder", metadata())
    with pytest.raises(WrongNodeKind):
        await deletion(context).check_delete_eligibility(caller(), node.id)
    with pytest.raises(WrongNodeKind):
        await deletion(context).delete_file(caller(), node.id, expected_revision=999)
    assert await context.namespace.get_node(node.id)


class GatedDeletionTransactions:
    def __init__(
        self, transactions: FilesystemTransactions, checked: asyncio.Event, release: asyncio.Event,
    ) -> None:
        self._transactions = transactions
        self._checked = checked
        self._release = release

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            namespace = create_autospec(NamespaceDriver, instance=True)
            namespace.get_node.side_effect = session.namespace.get_node

            async def delete_node(node_id: NodeId, *, expected_revision: int) -> None:
                self._checked.set()
                await self._release.wait()
                await session.namespace.delete_node(node_id, expected_revision=expected_revision)

            namespace.delete_node.side_effect = delete_node
            yield FilesystemSession(namespace=namespace, access_control=session.access_control)


@pytest.mark.asyncio
async def test_deletion_holds_serialized_transaction_from_authorization_through_cleanup(content_context: ContentContext) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), ROOT_ID, "file", metadata())
    await context.policies.add_grant(AccessGrant(node_id=node.id, principal=bob(), permissions={Permission.DISCOVER, Permission.DELETE}, recursive=False))
    checked, release, revoking = asyncio.Event(), asyncio.Event(), asyncio.Event()
    service = DeletionService(VerifiedIdentityResolver(), GatedDeletionTransactions(context.transactions, checked, release))

    async def revoke() -> None:
        revoking.set()
        await context.policies.remove_grant(node.id, bob())

    pending = asyncio.create_task(service.delete_file(snapshot("bob", "issuer", ()), node.id, expected_revision=node.revision))
    await checked.wait()
    revocation = asyncio.create_task(revoke())
    await revoking.wait()
    assert not revocation.done()
    release.set()
    await pending
    await revocation
    with pytest.raises(MissingNode):
        await context.namespace.get_node(node.id)
    assert await context.policies.list_grants(node.id) == []


class FailingCleanupTransactions:
    def __init__(self, transactions: FilesystemTransactions) -> None:
        self._transactions = transactions

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            policies = create_autospec(AccessControlDriver, instance=True)
            policies.get_owner.side_effect = session.access_control.get_owner
            policies.list_grants.side_effect = session.access_control.list_grants

            async def clear_node(node_id: NodeId) -> None:
                await session.access_control.clear_node(node_id)
                raise RuntimeError("cleanup failed")

            policies.clear_node.side_effect = clear_node
            yield FilesystemSession(namespace=session.namespace, access_control=policies)


@pytest.mark.asyncio
async def test_policy_cleanup_failure_rolls_back_namespace_owner_and_grants(content_context: ContentContext) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), ROOT_ID, "file", metadata())
    grant = AccessGrant(node_id=node.id, principal=bob(), permissions={Permission.READ}, recursive=False)
    await context.policies.add_grant(grant)
    owner = await context.policies.get_owner(node.id)
    service = DeletionService(VerifiedIdentityResolver(), FailingCleanupTransactions(context.transactions))
    with pytest.raises(StorageFailure):
        await service.delete_file(caller(), node.id, expected_revision=node.revision)
    assert (await context.namespace.get_node(node.id)).revision == node.revision
    assert await context.policies.get_owner(node.id) == owner
    assert await context.policies.list_grants(node.id) == [grant]


@pytest.mark.asyncio
async def test_namespace_and_policy_removal_ports_are_independent_and_revision_checked(content_context: ContentContext) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), ROOT_ID, "file", metadata())
    sibling = await context.creation.create_file(caller(), ROOT_ID, "sibling", metadata())
    for principal in (bob(), Principal(type=PrincipalType.GROUP, issuer="issuer", id="team")):
        await context.policies.add_grant(AccessGrant(node_id=node.id, principal=principal, permissions={Permission.READ}, recursive=True))
    sibling_grant = AccessGrant(node_id=sibling.id, principal=bob(), permissions={Permission.READ}, recursive=False)
    await context.policies.add_grant(sibling_grant)
    with pytest.raises(RevisionConflict):
        await context.namespace.delete_node(node.id, expected_revision=node.revision + 1)
    await context.namespace.delete_node(node.id, expected_revision=node.revision)
    assert await context.policies.get_owner(node.id)
    await context.policies.clear_node(node.id)
    await context.policies.clear_node(node.id)
    assert await context.policies.list_grants(node.id) == []
    assert await context.namespace.get_node(sibling.id)
    assert (await context.policies.get_owner(sibling.id)).owner == alice()
    assert await context.policies.list_grants(sibling.id) == [sibling_grant]
    with pytest.raises(OwnershipNotFound):
        await context.policies.get_owner(node.id)
    with pytest.raises(WrongNodeKind):
        await context.namespace.delete_node(ROOT_ID, expected_revision=1)
    with pytest.raises(MissingNode):
        await context.namespace.delete_node(node.id, expected_revision=node.revision)
