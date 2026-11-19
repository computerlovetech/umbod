from contextlib import AbstractAsyncContextManager

import pytest

from umbod.core.filesystem import AccessGrant, NodeKind, NodeMetadata, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.persistence import DatabaseSession, PersistenceRuntime, TransactionMode
from umbod.infrastructure import create_access_control_driver, create_filesystem_access, create_namespace_driver

from tests.support.filesystem.namespaces import personal_directory
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from tests.umbod.rest.user_catalogue.query_budget_support import CountingDatabase, QueryCounts


class IncomingShareReadAudit(CountingDatabase):
    def session(self, *, mode: TransactionMode) -> AbstractAsyncContextManager[DatabaseSession]:
        raise AssertionError("Incoming share discovery must not use a write-capable session")


@pytest.mark.asyncio
async def test_incoming_share_list_uses_one_read_only_snapshot(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    home = await personal_directory(database, snapshot("alice", "issuer", ()))
    node = await create_namespace_driver(database=database).create_node(
        home.id, "shared.txt", NodeKind.FILE, NodeMetadata(content_type={}, attributes={}),
    )
    bob = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    await create_access_control_driver(database=database).add_grant(AccessGrant(
        node_id=node.id, principal=bob, permissions={Permission.DISCOVER, Permission.READ}, recursive=False,
    ))
    counts = QueryCounts()
    service = create_filesystem_access(database=IncomingShareReadAudit(database, counts), resolver=VerifiedIdentityResolver())

    incoming = await service.list_shared_with_me(snapshot("bob", "issuer", ()))

    assert [item.id for item in incoming] == [node.id]
    assert counts.sessions == 1
    assert counts.writes == {}
