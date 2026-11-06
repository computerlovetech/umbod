from pathlib import Path

import pytest

from umbod.core.filesystem import SYSTEM_ROOT_OWNER, AccessGrant, Ownership, Permission, Principal, PrincipalType
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.stores.schema import (
    GRANT_ISSUER, GRANT_NODE, GRANT_PRINCIPAL, GRANT_TABLE, GRANT_TYPE,
    OWNER_NODE, OWNER_TABLE, GrantRecord, OwnershipRecord,
)
from umbod.core.persistence import AllFields, AllOf, DeleteQuery, Equals, InsertCommand, NoFilter, Query, TransactionMode, Unordered
from tests.persistence_runtime import prepared_sqlite_runtime


@pytest.mark.asyncio
async def test_sqlite_root_completion_ownership_and_grant_deletion_survive_runtime_recreation(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap.sqlite"
    owner = OwnershipRecord(
        node_id=str(ROOT_ID), payload=Ownership(node_id=ROOT_ID, owner=SYSTEM_ROOT_OWNER),
    )
    removed_grant = GrantRecord(
        node_id=str(ROOT_ID), principal_type="user", issuer="issuer", principal_id="alice",
        payload=AccessGrant(
            node_id=ROOT_ID, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"),
            permissions={Permission.DISCOVER, Permission.WRITE}, recursive=False,
        ),
    )
    retained_grant = GrantRecord(
        node_id=str(ROOT_ID), principal_type="user", issuer="foreign", principal_id="alice",
        payload=AccessGrant(
            node_id=ROOT_ID, principal=Principal(type=PrincipalType.USER, issuer="foreign", id="alice"),
            permissions={Permission.READ}, recursive=True,
        ),
    )
    removed_filter = AllOf((
        Equals(GRANT_NODE, removed_grant.node_id), Equals(GRANT_TYPE, removed_grant.principal_type),
        Equals(GRANT_ISSUER, removed_grant.issuer), Equals(GRANT_PRINCIPAL, removed_grant.principal_id),
    ))
    runtime = await prepared_sqlite_runtime(path)
    try:
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            assert await session.insert(OWNER_TABLE, InsertCommand(row=owner))
            assert await session.insert(GRANT_TABLE, InsertCommand(row=removed_grant))
            assert await session.insert(GRANT_TABLE, InsertCommand(row=retained_grant))
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            assert await session.delete(GRANT_TABLE, DeleteQuery(filter=removed_filter)) == 1
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        async with reopened.database.read_session() as session:
            assert await session.find_one(
                OWNER_TABLE, Query(Equals(OWNER_NODE, str(ROOT_ID)), AllFields(), Unordered()),
            ) == owner
            assert await session.find_one(GRANT_TABLE, Query(removed_filter, AllFields(), Unordered())) is None
            assert await session.find_many(GRANT_TABLE, Query(NoFilter(), AllFields(), Unordered())) == (retained_grant,)
    finally:
        await reopened.shutdown()
