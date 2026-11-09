from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TypeVar

import pytest
from pydantic import BaseModel

from umbod.core.filesystem import AccessGrant, NodeKind, NodeMetadata, Ownership, Permission, PrincipalType
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.namespace import ROOT_ID, initial_root
from umbod.core.filesystem.stores.namespace import node_record
from umbod.core.filesystem.stores.schema import NODE_TABLE, OWNER_TABLE, GRANT_TABLE, OwnershipRecord, GrantRecord
from umbod.core.persistence import DatabaseSession, InsertCommand, OneOf, PersistenceRuntime, Query, ReadSession, Table, TransactionMode
from umbod.infrastructure import create_access_control_driver, create_filesystem_explorer, create_namespace_driver
from tests.umbod.rest.user_catalogue.query_budget_support import CountingDatabase, CountingReadSession, QueryCounts
from tests.support.filesystem.authorization import principal, caller
from tests.support.filesystem.exploration import CountingIdentityResolver, child

RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


class ScopedReadAudit(CountingReadSession):
    async def find_many(self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]) -> Sequence[ResultT]:
        if table.name in {"filesystem_ownership", "filesystem_grants"}:
            assert isinstance(query.filter, OneOf)
            assert 0 < len(query.filter.values) <= 200
        return await super().find_many(table, query)


class ReadOnlyAuditDatabase(CountingDatabase):
    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[ReadSession]:
        self.counts.sessions += 1
        async with self.database.read_session() as session:
            yield ScopedReadAudit(session, self.counts)

    def session(self, *, mode: TransactionMode) -> AbstractAsyncContextManager[DatabaseSession]:
        raise AssertionError("Browsing must not open a write-capable session")


async def seed_directory(runtime: PersistenceRuntime, count: int) -> None:
    root = initial_root()
    user = principal("alice", PrincipalType.USER, "issuer")
    nodes = [root, *(child(ROOT_ID, f"file-{index:04}", NodeKind.FILE) for index in range(count))]
    async with runtime.database.session(mode=TransactionMode.READ_WRITE) as session:
        for node in nodes:
            await session.insert(NODE_TABLE, InsertCommand(row=node_record(node)))
            await session.insert(OWNER_TABLE, InsertCommand(row=OwnershipRecord(
                node_id=str(node.id), payload=Ownership(node_id=node.id, owner=user),
            )))
        grant = AccessGrant(node_id=ROOT_ID, principal=user, permissions=set(Permission), recursive=False)
        await session.insert(GRANT_TABLE, InsertCommand(row=GrantRecord(
            node_id=str(ROOT_ID), principal_type=user.type.value, issuer=user.issuer, principal_id=user.id, payload=grant,
        )))


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 40, 100, 200, 401, 1001])
async def test_complete_scoped_listing_has_one_read_only_session_and_bounded_policy_batches(
    filesystem_runtime: PersistenceRuntime, count: int,
) -> None:
    await seed_directory(filesystem_runtime, count)
    counts = QueryCounts()
    database = ReadOnlyAuditDatabase(filesystem_runtime.database, counts)
    resolver = CountingIdentityResolver(True)
    explorer = create_filesystem_explorer(database=database, resolver=resolver, sharing_available=True)
    result = await explorer.browse_node(caller("alice"), ROOT_ID)
    batches = 1 + (count + 199) // 200
    assert len(result.entries) == count
    assert result.truncated is False
    assert counts.sessions == resolver.calls == 1
    assert counts.reads == {"filesystem_nodes": 2, "filesystem_ownership": batches, "filesystem_grants": batches}
    assert counts.writes == {}
    assert counts.schema_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", [1, 40, 100])
@pytest.mark.parametrize("kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_shared_target_reads_hidden_ancestry_without_disclosing_it(
    filesystem_runtime: PersistenceRuntime, depth: int, kind: NodeKind,
) -> None:
    user = principal("alice", PrincipalType.USER, "issuer")
    other = principal("bob", PrincipalType.USER, "issuer")
    nodes = [initial_root()]
    for index in range(depth):
        nodes.append(child(nodes[-1].id, f"ancestor-{index}", NodeKind.DIRECTORY))
    hidden_parent = nodes[-1]
    target = child(hidden_parent.id, "shared-target", kind)
    nodes.append(target)
    async with filesystem_runtime.database.session(mode=TransactionMode.READ_WRITE) as session:
        for node in nodes:
            await session.insert(NODE_TABLE, InsertCommand(row=node_record(node)))
            await session.insert(OWNER_TABLE, InsertCommand(row=OwnershipRecord(
                node_id=str(node.id), payload=Ownership(
                    node_id=node.id, owner=other if node.id in {hidden_parent.id, target.id} else user,
                ),
            )))
        grant = AccessGrant(
            node_id=target.id, principal=user,
            permissions={Permission.DISCOVER, Permission.WRITE}, recursive=False,
        )
        await session.insert(GRANT_TABLE, InsertCommand(row=GrantRecord(
            node_id=str(target.id), principal_type=user.type.value, issuer=user.issuer,
            principal_id=user.id, payload=grant,
        )))
    counts = QueryCounts()
    resolver = CountingIdentityResolver(True)
    explorer = create_filesystem_explorer(
        database=ReadOnlyAuditDatabase(filesystem_runtime.database, counts),
        resolver=resolver, sharing_available=False,
    )
    result = await explorer.browse_node(caller("alice"), target.id)
    assert result.entries == []
    assert result.breadcrumbs.complete is False
    assert [item.id for item in result.breadcrumbs.items] == [target.id]
    assert str(hidden_parent.id) not in result.breadcrumbs.model_dump_json()
    assert result.capabilities[0].rename is True
    assert result.capabilities[0].move is False
    assert counts.sessions == resolver.calls == 1
    assert counts.reads == {
        "filesystem_nodes": depth + (3 if kind == NodeKind.DIRECTORY else 2),
        "filesystem_ownership": 1, "filesystem_grants": 1,
    }
    assert counts.writes == {}


@pytest.mark.asyncio
async def test_absent_canonical_root_is_denied_without_provisioning_or_writes(filesystem_runtime: PersistenceRuntime) -> None:
    counts = QueryCounts()
    explorer = create_filesystem_explorer(
        database=ReadOnlyAuditDatabase(filesystem_runtime.database, counts),
        resolver=CountingIdentityResolver(True), sharing_available=False,
    )
    with pytest.raises(PermissionDenied):
        await explorer.browse_node(caller("alice"), ROOT_ID)
    assert counts.sessions == 1
    assert counts.reads == {"filesystem_nodes": 1}
    assert counts.writes == {}
    async with filesystem_runtime.database.read_session() as session:
        from umbod.core.persistence import AllFields, Equals, Unordered
        from umbod.core.filesystem.stores.schema import NODE_ID
        root = await session.find_one(NODE_TABLE, Query(
            filter=Equals(NODE_ID, str(ROOT_ID)), projection=AllFields(), ordering=Unordered(),
        ))
    assert root is None


@pytest.mark.asyncio
async def test_denied_directory_does_not_enumerate_children_or_read_their_policies(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    await seed_directory(filesystem_runtime, 100)
    await create_access_control_driver(database=filesystem_runtime.database).clear_node(ROOT_ID)
    counts = QueryCounts()
    explorer = create_filesystem_explorer(
        database=ReadOnlyAuditDatabase(filesystem_runtime.database, counts),
        resolver=CountingIdentityResolver(True), sharing_available=True,
    )
    with pytest.raises(PermissionDenied):
        await explorer.browse_node(caller("alice"), ROOT_ID)
    assert counts.sessions == 1
    assert counts.reads == {"filesystem_nodes": 1, "filesystem_ownership": 1, "filesystem_grants": 1}
    assert counts.writes == {}


@pytest.mark.asyncio
async def test_scoped_database_permissions_preserve_partial_ancestry_and_hide_ownerless_entries(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    namespace = create_namespace_driver(database=filesystem_runtime.database)
    policies = create_access_control_driver(database=filesystem_runtime.database)
    user = principal("alice", PrincipalType.USER, "issuer")
    root = await namespace.get_root()
    parent = await namespace.create_node(
        root.id, "hidden", NodeKind.DIRECTORY, NodeMetadata(content_type="text/plain", attributes={}),
    )
    target = await namespace.create_node(
        parent.id, "shared", NodeKind.DIRECTORY, NodeMetadata(content_type="text/plain", attributes={}),
    )
    ownerless = await namespace.create_node(
        target.id, "ownerless", NodeKind.FILE, NodeMetadata(content_type="text/plain", attributes={}),
    )
    for node in (root, target):
        await policies.set_owner(Ownership(node_id=node.id, owner=user))
    await policies.set_owner(Ownership(
        node_id=parent.id, owner=principal("bob", PrincipalType.USER, "issuer"),
    ))
    await policies.add_grant(AccessGrant(
        node_id=ownerless.id, principal=user, permissions=set(Permission), recursive=False,
    ))
    counts = QueryCounts()
    explorer = create_filesystem_explorer(
        database=ReadOnlyAuditDatabase(filesystem_runtime.database, counts),
        resolver=CountingIdentityResolver(True), sharing_available=False,
    )
    result = await explorer.browse_node(caller("alice"), target.id)
    assert result.entries == []
    assert result.breadcrumbs.complete is False
    assert [item.id for item in result.breadcrumbs.items] == [target.id]
    assert result.capabilities[0].rename is True
    assert result.capabilities[0].move is result.capabilities[0].share is False
    assert counts.sessions == 1
    assert counts.writes == {}
