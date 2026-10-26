import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
import pytest_asyncio

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import (
    AccessControlDriver,
    AccessGrant,
    CreationService,
    FilesystemCreation,
    FilesystemSession,
    FilesystemTransactions,
    InvalidName,
    NameCollision,
    NamespaceDriver,
    Node,
    NodeId,
    NodeKind,
    NodeMetadata,
    Ownership,
    OwnershipNotFound,
    Permission,
    Principal,
    PrincipalType,
    RootBootstrapGrant,
    RootBootstrapSpec,
    StorageFailure,
    UnspecifiedContentType,
    WrongNodeKind,
)
from umbod.core.filesystem.authorization import (
    AuthorizationService,
    FilesystemAuthorization,
    FilesystemIdentityResolver,
    PermissionDenied,
    ResolvedIdentity,
    UnresolvedIdentity,
    VerifiedIdentityResolver,
)
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    create_access_control_driver,
    create_filesystem_creation,
    create_filesystem_transactions,
    create_namespace_driver,
    create_root_provisioning,
)
from tests.support.filesystem.transaction_observations import RecordingTransactions
from tests.umbod.core.filesystem.test_database_persistence import FailingCommitDatabase
from tests.umbod.core.filesystem.test_verified_identity import snapshot


def metadata() -> NodeMetadata:
    return NodeMetadata(content_type=UnspecifiedContentType(), attributes={"tag": "safe"})


def user(identifier: str) -> Principal:
    return Principal(type=PrincipalType.USER, issuer="issuer", id=identifier)


@dataclass(frozen=True)
class CreationContext:
    creation: FilesystemCreation
    authorization: FilesystemAuthorization
    namespace: NamespaceDriver
    policies: AccessControlDriver
    transactions: FilesystemTransactions
    resolver: Mock


@pytest_asyncio.fixture
async def creation_context(filesystem_runtime: PersistenceRuntime) -> CreationContext:
    database = filesystem_runtime.database
    namespace = create_namespace_driver(database=database)
    policies = create_access_control_driver(database=database)
    resolver = create_autospec(FilesystemIdentityResolver, instance=True)
    resolver.resolve.side_effect = VerifiedIdentityResolver().resolve
    await create_root_provisioning(database=database).provision(RootBootstrapSpec(grants=(
        RootBootstrapGrant(principal=user("alice"), permissions=frozenset({Permission.DISCOVER, Permission.WRITE})),
    )))
    return CreationContext(
        creation=create_filesystem_creation(database=database, resolver=resolver),
        authorization=AuthorizationService(resolver, namespace, policies),
        namespace=namespace, policies=policies,
        transactions=create_filesystem_transactions(database=database), resolver=resolver,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(NodeKind))
async def test_creation_assigns_only_creator_and_no_child_grants(creation_context: CreationContext, kind: NodeKind) -> None:
    context = creation_context
    caller = snapshot("alice", "issuer", ("team",))
    operation = context.creation.create_file if kind == NodeKind.FILE else context.creation.create_directory
    supplied = metadata()
    child = await operation(caller, ROOT_ID, "child", supplied)
    context.resolver.resolve.assert_awaited_once_with(caller)
    assert child.kind == kind
    assert not hasattr(child, "content")
    assert (await context.policies.get_owner(child.id)).owner == user("alice")
    assert await context.policies.list_grants(child.id) == []
    supplied.attributes.clear()
    child.metadata.attributes["tag"] = "changed"
    assert (await context.namespace.get_node(child.id)).metadata.attributes == {"tag": "safe"}
    for permission in Permission:
        assert (await context.authorization.decide(caller, child.id, permission)).allowed
        assert not (await context.authorization.decide(snapshot("bob", "issuer", ("team",)), child.id, permission)).allowed


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [frozenset(), frozenset({Permission.READ}), frozenset({Permission.DISCOVER}), frozenset({Permission.WRITE})])
async def test_parent_requires_both_discover_and_write(creation_context: CreationContext, permissions: frozenset[Permission]) -> None:
    context = creation_context
    await context.policies.add_grant(AccessGrant(node_id=ROOT_ID, principal=user("alice"), permissions=set(permissions), recursive=False))
    with pytest.raises(PermissionDenied):
        await context.creation.create_file(snapshot("alice", "issuer", ()), ROOT_ID, "denied", metadata())
    assert await context.namespace.list_children(ROOT_ID) == []


@pytest.mark.asyncio
async def test_group_parent_grant_allows_creation_without_inheritance(creation_context: CreationContext) -> None:
    context = creation_context
    team = Principal(type=PrincipalType.GROUP, issuer="issuer", id="team")
    await context.policies.remove_grant(ROOT_ID, user("alice"))
    await context.policies.add_grant(AccessGrant(node_id=ROOT_ID, principal=team, permissions={Permission.DISCOVER, Permission.WRITE}, recursive=True))
    child = await context.creation.create_directory(snapshot("alice", "issuer", ("team",)), ROOT_ID, "group-created", metadata())
    assert (await context.policies.get_owner(child.id)).owner == user("alice")
    assert await context.policies.list_grants(child.id) == []
    assert not (await context.authorization.decide(snapshot("bob", "issuer", ("team",)), child.id, Permission.DISCOVER)).allowed
    with pytest.raises(PermissionDenied):
        await context.creation.create_file(snapshot("alice", "issuer", ()), ROOT_ID, "revoked-group", metadata())


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [True, False])
async def test_missing_and_unowned_parent_are_denied(creation_context: CreationContext, missing: bool) -> None:
    context = creation_context
    parent_id = uuid4() if missing else (await context.namespace.create_node(ROOT_ID, "unowned", NodeKind.DIRECTORY, metadata())).id
    with pytest.raises(PermissionDenied):
        await context.creation.create_file(snapshot("alice", "issuer", ()), parent_id, "denied", metadata())


@pytest.mark.asyncio
async def test_authorized_file_parent_reports_kind_and_name_errors_are_preserved(creation_context: CreationContext) -> None:
    context = creation_context
    caller = snapshot("alice", "issuer", ())
    file = await context.creation.create_file(caller, ROOT_ID, "file", metadata())
    with pytest.raises(WrongNodeKind):
        await context.creation.create_directory(caller, file.id, "child", metadata())
    with pytest.raises(InvalidName):
        await context.creation.create_file(caller, ROOT_ID, "a/b", metadata())
    with pytest.raises(NameCollision):
        await context.creation.create_directory(caller, ROOT_ID, "file", metadata())
    assert len(await context.namespace.list_children(ROOT_ID)) == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_create_has_one_owned_winner(creation_context: CreationContext) -> None:
    context = creation_context
    results = await asyncio.gather(*(
        context.creation.create_file(snapshot("alice", "issuer", ()), ROOT_ID, "same", metadata()) for _ in range(2)
    ), return_exceptions=True)
    winners = [result for result in results if isinstance(result, NodeSummary)]
    assert len(winners) == 1
    assert sum(isinstance(result, NameCollision) for result in results) == 1
    assert (await context.policies.get_owner(winners[0].id)).owner == user("alice")
    assert [node.id for node in await context.namespace.list_children(ROOT_ID)] == [winners[0].id]


@pytest.mark.asyncio
async def test_unresolved_snapshot_does_not_open_transaction() -> None:
    transactions = create_autospec(FilesystemTransactions, instance=True)
    creation: FilesystemCreation = CreationService(VerifiedIdentityResolver(), transactions)
    with pytest.raises(PermissionDenied):
        await creation.create_file(snapshot("alice", "issuer", ("",)), ROOT_ID, "denied", metadata())
    assert transactions.mock_calls == []


class FailingOwnershipTransactions:
    def __init__(self, transactions: FilesystemTransactions, failure: BaseException) -> None:
        self._transactions = transactions
        self._failure = failure

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            policies = create_autospec(AccessControlDriver, instance=True)
            policies.get_owner.side_effect = session.access_control.get_owner
            policies.list_grants.side_effect = session.access_control.list_grants
            policies.set_owner.side_effect = self._failure
            yield FilesystemSession(namespace=session.namespace, access_control=policies)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
@pytest.mark.parametrize("point", ["ownership", "commit"])
async def test_failure_and_cancellation_leave_no_orphan_node_or_owner(
    filesystem_runtime: PersistenceRuntime, creation_context: CreationContext, cancelled: bool, point: str,
) -> None:
    context = creation_context
    failure = asyncio.CancelledError() if cancelled else RuntimeError("failed ownership")
    transactions = FailingOwnershipTransactions(context.transactions, failure) if point == "ownership" else create_filesystem_transactions(database=FailingCommitDatabase(filesystem_runtime.database, cancelled))
    recorded = RecordingTransactions(transactions)
    creation: FilesystemCreation = CreationService(VerifiedIdentityResolver(), recorded)
    with pytest.raises(asyncio.CancelledError if cancelled else StorageFailure):
        await creation.create_file(snapshot("alice", "issuer", ()), ROOT_ID, "rolled-back", metadata())
    assert await context.namespace.list_children(ROOT_ID) == []
    assert len(recorded.created) == 1
    with pytest.raises(OwnershipNotFound):
        await context.policies.get_owner(recorded.created[0])
    child = await context.creation.create_file(snapshot("alice", "issuer", ()), ROOT_ID, "rolled-back", metadata())
    assert (await context.policies.get_owner(child.id)).owner == user("alice")


class ObservedResolver:
    def __init__(self, resolved: asyncio.Event) -> None:
        self._resolved = resolved

    async def resolve(self, caller: CallerSnapshot) -> ResolvedIdentity | UnresolvedIdentity:
        identity = await VerifiedIdentityResolver().resolve(caller)
        self._resolved.set()
        return identity


@pytest.mark.asyncio
async def test_parent_authorization_reads_revocation_committed_before_transaction(creation_context: CreationContext) -> None:
    context = creation_context
    resolved = asyncio.Event()
    creation: FilesystemCreation = CreationService(ObservedResolver(resolved), context.transactions)
    async with context.transactions.transaction() as session:
        await session.access_control.remove_grant(ROOT_ID, user("alice"))
        pending = asyncio.create_task(creation.create_file(snapshot("alice", "issuer", ()), ROOT_ID, "revoked", metadata()))
        await resolved.wait()
    with pytest.raises(PermissionDenied):
        await pending
    assert await context.namespace.list_children(ROOT_ID) == []


class GatedCreationTransactions:
    def __init__(self, transactions: FilesystemTransactions, entered: asyncio.Event, release: asyncio.Event) -> None:
        self._transactions = transactions
        self._entered = entered
        self._release = release

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            namespace = create_autospec(NamespaceDriver, instance=True)
            namespace.get_node.side_effect = session.namespace.get_node

            async def create(parent_id: NodeId, name: str, kind: NodeKind, metadata: NodeMetadata) -> Node:
                self._entered.set()
                await self._release.wait()
                return await session.namespace.create_node(parent_id, name, kind, metadata)

            namespace.create_node.side_effect = create
            yield FilesystemSession(namespace=namespace, access_control=session.access_control)


@pytest.mark.asyncio
async def test_creation_holds_serialized_transaction_between_authorization_and_owner_assignment(creation_context: CreationContext) -> None:
    context = creation_context
    checked = asyncio.Event()
    release = asyncio.Event()
    revoking = asyncio.Event()
    creation: FilesystemCreation = CreationService(VerifiedIdentityResolver(), GatedCreationTransactions(context.transactions, checked, release))

    async def revoke() -> None:
        revoking.set()
        await context.policies.remove_grant(ROOT_ID, user("alice"))

    pending = asyncio.create_task(creation.create_file(snapshot("alice", "issuer", ()), ROOT_ID, "before-revoke", metadata()))
    await checked.wait()
    revocation = asyncio.create_task(revoke())
    await revoking.wait()
    assert not revocation.done()
    release.set()
    child = await pending
    await revocation
    assert (await context.policies.get_owner(child.id)).owner == user("alice")
    with pytest.raises(PermissionDenied):
        await context.creation.create_file(snapshot("alice", "issuer", ()), ROOT_ID, "after-revoke", metadata())


class ReusedIdentityTransactions:
    def __init__(self, transactions: FilesystemTransactions, reused_id: NodeId) -> None:
        self._transactions = transactions
        self._reused_id = reused_id
        self.inserted: list[NodeId] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            namespace = create_autospec(NamespaceDriver, instance=True)
            namespace.get_node.side_effect = session.namespace.get_node

            async def create(parent_id: NodeId, name: str, kind: NodeKind, metadata: NodeMetadata) -> Node:
                node = await session.namespace.create_node(parent_id, name, kind, metadata)
                self.inserted.append(node.id)
                return node.model_copy(update={"id": self._reused_id})

            namespace.create_node.side_effect = create
            yield FilesystemSession(namespace=namespace, access_control=session.access_control)


@pytest.mark.asyncio
@pytest.mark.parametrize("orphan", ["owner", "grant"])
async def test_returned_uuid_with_orphan_policies_rolls_back_without_modifying_policies(creation_context: CreationContext, orphan: str) -> None:
    context = creation_context
    reused_id = uuid4()
    ownership = Ownership(node_id=reused_id, owner=user("legacy"))
    grants = [AccessGrant(node_id=reused_id, principal=user("legacy"), permissions={Permission.READ}, recursive=False)] if orphan == "grant" else []
    if orphan == "owner":
        await context.policies.set_owner(ownership)
    else:
        await context.policies.add_grant(grants[0])
    transactions = ReusedIdentityTransactions(context.transactions, reused_id)
    creation: FilesystemCreation = CreationService(VerifiedIdentityResolver(), transactions)
    with pytest.raises(StorageFailure, match="New node has pre-existing policies"):
        await creation.create_file(snapshot("alice", "issuer", ()), ROOT_ID, "reused", metadata())
    assert await context.namespace.list_children(ROOT_ID) == []
    assert len(transactions.inserted) == 1
    with pytest.raises(OwnershipNotFound):
        await context.policies.get_owner(transactions.inserted[0])
    assert await context.policies.list_grants(reused_id) == grants
    if orphan == "owner":
        assert await context.policies.get_owner(reused_id) == ownership
    else:
        with pytest.raises(OwnershipNotFound):
            await context.policies.get_owner(reused_id)
