from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import TypeVar
from unittest.mock import Mock

import pytest
from pydantic import BaseModel

from umbod.core.filesystem import AccessGrant, NodeKind, Ownership, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import AuthorizationService, VerifiedIdentityResolver
from umbod.core.filesystem.errors import PolicyDecodingFailure
from umbod.core.filesystem.stores import DatabaseFilesystemAuthorizationReader
from umbod.core.persistence import Database, DatabaseSession, PersistenceDecodingError, PersistenceRuntime, Query, ReadSession, Table, TransactionMode
from umbod.infrastructure import create_access_control_driver, create_filesystem_browsing, create_filesystem_creation, create_filesystem_explorer, create_namespace_driver
from tests.support.filesystem.namespaces import shared_directory
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from tests.umbod.rest.user_catalogue.query_budget_support import CountingDatabase, CountingReadSession, QueryCounts

RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


class DormantAclGuardSession(CountingReadSession):
    def __init__(self, session: ReadSession, counts: QueryCounts, dormant_ids: frozenset[str]) -> None:
        super().__init__(session, counts)
        self._dormant_ids = dormant_ids

    def _validate_rows(self, table_name: str, rows: Sequence[BaseModel]) -> None:
        if table_name in {"filesystem_ownership", "filesystem_grants"} and any(row.model_dump().get("node_id") in self._dormant_ids for row in rows):
            raise PersistenceDecodingError(table_name, "payload", ValueError("Malformed dormant ACL"))

    async def find_one(self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]) -> ResultT | None:
        row = await super().find_one(table, query)
        self._validate_rows(table.name, () if row is None else (row,))
        return row

    async def find_many(self, table: Table[RowT, KeyT], query: Query[RowT, ResultT]) -> Sequence[ResultT]:
        rows = await super().find_many(table, query)
        self._validate_rows(table.name, rows)
        return rows


class DormantAclGuardDatabase(CountingDatabase):
    def __init__(self, database: Database, counts: QueryCounts, dormant_ids: frozenset[str]) -> None:
        super().__init__(database, counts)
        self._dormant_ids = dormant_ids

    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[ReadSession]:
        self.counts.sessions += 1
        async with self.database.read_session() as session:
            yield DormantAclGuardSession(session, self.counts, self._dormant_ids)

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        self.counts.sessions += 1
        async with self.database.session(mode=mode) as session:
            guarded = DormantAclGuardSession(session, self.counts, self._dormant_ids)
            observed = Mock(spec=DatabaseSession, wraps=session)
            observed.find_one.side_effect = guarded.find_one
            observed.find_many.side_effect = guarded.find_many
            yield observed


@pytest.mark.asyncio
async def test_authorization_read_models_never_decode_dormant_anchor_namespace_root_or_unmanaged_acls(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    root = await shared_directory(database)
    creator = snapshot("alice", "issuer", ("team",))
    child = await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_directory(creator, root.id, "Child", root.metadata)
    namespace = create_namespace_driver(database=database)
    anchor = await namespace.get_root()
    unmanaged = await namespace.create_node(anchor.id, "Unmanaged", NodeKind.DIRECTORY, root.metadata)
    unmanaged_leaf = await namespace.create_node(unmanaged.id, "File", NodeKind.FILE, root.metadata)
    policies = create_access_control_driver(database=database)
    guest = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    dormant_nodes = (anchor, root, unmanaged, unmanaged_leaf)
    for node in dormant_nodes:
        await policies.set_owner(Ownership(node_id=node.id, owner=guest))
        await policies.add_grant(AccessGrant(node_id=node.id, principal=guest, permissions=set(Permission), recursive=True))
    await policies.add_grant(AccessGrant(node_id=child.id, principal=guest, permissions={Permission.DISCOVER, Permission.READ}, recursive=True))
    counts = QueryCounts()
    guarded = DormantAclGuardDatabase(database, counts, frozenset(str(node.id) for node in dormant_nodes))
    guarded_policies = create_access_control_driver(database=guarded)
    authorization = AuthorizationService(VerifiedIdentityResolver(), namespace, guarded_policies)
    actor = snapshot("bob", "issuer", ())
    assert (await authorization.decide(actor, child.id, Permission.READ)).allowed
    for node in dormant_nodes:
        assert not (await authorization.decide(actor, node.id, Permission.READ)).allowed
    projection = await DatabaseFilesystemAuthorizationReader(guarded).read()
    assert {owner.node_id for owner in projection.ownerships} == {child.id}
    assert {grant.node_id for grant in projection.grants} == {child.id}
    result = await create_filesystem_explorer(database=guarded, resolver=VerifiedIdentityResolver()).browse_node(actor, child.id)
    assert result.node.id == child.id
    assert not result.breadcrumbs.complete
    assert [item.id for item in result.breadcrumbs.items] == [child.id]
    assert (await create_filesystem_browsing(database=guarded, resolver=VerifiedIdentityResolver()).get_node(actor, child.id)).id == child.id
    with pytest.raises(PolicyDecodingFailure):
        await guarded_policies.list_grants(anchor.id)
