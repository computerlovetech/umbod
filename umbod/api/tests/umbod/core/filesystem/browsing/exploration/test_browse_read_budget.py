from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TypeVar

import pytest
from pydantic import BaseModel

from umbod.core.filesystem import NodeId, NodeKind, NodeMetadata
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.stores.namespace import node_record
from umbod.core.filesystem.stores.namespaces import persist_policy
from umbod.core.filesystem.stores.schema import NODE_TABLE
from umbod.core.persistence import DatabaseSession, InsertCommand, PersistenceRuntime, Query, ReadSession, Table, TransactionMode, OneOf
from umbod.infrastructure import create_filesystem_explorer, create_namespace_driver
from tests.umbod.rest.user_catalogue.query_budget_support import CountingDatabase, CountingReadSession, QueryCounts
from tests.support.filesystem.authorization import caller
from tests.support.filesystem.exploration import CountingIdentityResolver, child
from tests.support.filesystem.namespaces import personal_directory
from tests.umbod.core.filesystem.test_effective_permissions import policy
from tests.umbod.core.filesystem.test_verified_identity import snapshot

RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


class ScopedReadAudit(CountingReadSession):
    async def find_many(self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]) -> Sequence[ResultT]:
        if table.name in {"filesystem_ownership", "filesystem_grants"}:
            assert isinstance(query.filter, OneOf)
            assert 0 < len(query.filter.values) <= 200
            assert str(ROOT_ID) not in query.filter.values
        return await super().find_many(table, query)


class ReadOnlyAuditDatabase(CountingDatabase):
    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[ReadSession]:
        self.counts.sessions += 1
        async with self.database.read_session() as session:
            yield ScopedReadAudit(session, self.counts)

    def session(self, *, mode: TransactionMode) -> AbstractAsyncContextManager[DatabaseSession]:
        raise AssertionError("Browsing must not open a write-capable session")


async def seed_directory(runtime: PersistenceRuntime, count: int) -> NodeId:
    root = await personal_directory(runtime.database, snapshot("alice", "issuer", ()))
    async with runtime.database.session(mode=TransactionMode.READ_WRITE) as session:
        for index in range(count):
            await session.insert(NODE_TABLE, InsertCommand(row=node_record(child(root.id, f"file-{index:04}", NodeKind.FILE))))
    return root.id


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 40, 100, 200, 401, 1001])
async def test_complete_listing_reads_scoped_acls_in_bounded_batches(
    filesystem_runtime: PersistenceRuntime, count: int,
) -> None:
    root_id = await seed_directory(filesystem_runtime, count)
    counts = QueryCounts()
    resolver = CountingIdentityResolver(True)
    explorer = create_filesystem_explorer(database=ReadOnlyAuditDatabase(filesystem_runtime.database, counts), resolver=resolver)
    result = await explorer.browse_node(caller("alice"), root_id)
    assert len(result.entries) == count
    assert not result.truncated
    assert counts.sessions == resolver.calls == 1
    batches = (count + 199) // 200
    assert counts.reads == {"filesystem_nodes": 3, "filesystem_namespaces": 1, "filesystem_ownership": batches, "filesystem_grants": batches}
    assert counts.writes == {}
    assert counts.schema_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", [1, 40, 100])
@pytest.mark.parametrize("kind", list(NodeKind))
async def test_namespace_boundary_hides_structural_ancestry_but_requires_complete_lineage(
    filesystem_runtime: PersistenceRuntime, depth: int, kind: NodeKind,
) -> None:
    namespace = create_namespace_driver(database=filesystem_runtime.database)
    hidden = await namespace.get_root()
    for index in range(depth):
        hidden = await namespace.create_node(hidden.id, f"ancestor-{index}", NodeKind.DIRECTORY, NodeMetadata(content_type={}, attributes={}))
    root = await namespace.create_node(hidden.id, "namespace", NodeKind.DIRECTORY, hidden.metadata)
    target = await namespace.create_node(root.id, "target", kind, root.metadata)
    async with filesystem_runtime.database.session(mode=TransactionMode.READ_WRITE) as session:
        await persist_policy(session, policy(root.id))
    counts = QueryCounts()
    resolver = CountingIdentityResolver(True)
    explorer = create_filesystem_explorer(database=ReadOnlyAuditDatabase(filesystem_runtime.database, counts), resolver=resolver)
    result = await explorer.browse_node(caller("alice"), target.id)
    assert result.entries == []
    assert result.breadcrumbs.complete
    assert [item.id for item in result.breadcrumbs.items] == [root.id, target.id]
    assert str(hidden.id) not in result.breadcrumbs.model_dump_json()
    assert result.capabilities[0].rename
    assert result.capabilities[0].move
    assert counts.sessions == resolver.calls == 1
    assert counts.reads == {"filesystem_nodes": depth + (4 if kind == NodeKind.DIRECTORY else 3), "filesystem_namespaces": 1, "filesystem_ownership": 1, "filesystem_grants": 1}
    assert counts.writes == {}


@pytest.mark.asyncio
async def test_absent_structural_root_denies_without_writes(filesystem_runtime: PersistenceRuntime) -> None:
    counts = QueryCounts()
    explorer = create_filesystem_explorer(database=ReadOnlyAuditDatabase(filesystem_runtime.database, counts), resolver=CountingIdentityResolver(True))
    with pytest.raises(PermissionDenied):
        await explorer.browse_node(caller("alice"), ROOT_ID)
    assert counts.sessions == 1
    assert counts.reads == {"filesystem_nodes": 1}
    assert counts.writes == {}


@pytest.mark.asyncio
async def test_structural_root_denial_does_not_enumerate_children(filesystem_runtime: PersistenceRuntime) -> None:
    await seed_directory(filesystem_runtime, 100)
    counts = QueryCounts()
    explorer = create_filesystem_explorer(database=ReadOnlyAuditDatabase(filesystem_runtime.database, counts), resolver=CountingIdentityResolver(True))
    with pytest.raises(PermissionDenied):
        await explorer.browse_node(caller("alice"), ROOT_ID)
    assert counts.sessions == 1
    assert counts.reads == {"filesystem_nodes": 1, "filesystem_namespaces": 1}
    assert counts.writes == {}
