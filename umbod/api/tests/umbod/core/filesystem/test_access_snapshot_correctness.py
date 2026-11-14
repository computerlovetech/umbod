from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from umbod.core.filesystem.access import AccessMetadataService
from umbod.core.filesystem.access.service import project_mutation_result_access
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.errors import StorageFailure
from umbod.core.filesystem.models import AccessGrant, NodeId, Permission, Principal, PrincipalType
from umbod.core.filesystem.transactions import FilesystemSession, FilesystemTransactions
from umbod.core.filesystem.updates import NodeChanges, NodeUpdateService
from umbod.core.persistence import Database, PersistenceRuntime
from umbod.infrastructure import create_access_control_driver, create_filesystem_creation, create_filesystem_transactions, create_namespace_driver
from tests.support.filesystem.access_snapshots import fail_stored_grant_decoding
from tests.support.filesystem.namespaces import personal_directory, shared_directory, set_shared_access
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_undecodable_raw_grants_do_not_affect_registered_namespace_authority(
    filesystem_runtime: PersistenceRuntime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    root = await personal_directory(database, caller)
    node = await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_file(caller, root.id, "file", root.metadata)
    await create_access_control_driver(database=database).add_grant(AccessGrant(
        node_id=node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"), permissions=set(Permission), recursive=False,
    ))
    fail_stored_grant_decoding(database, node.id, monkeypatch)
    transactions = create_filesystem_transactions(database=database)
    projected = (await AccessMetadataService(VerifiedIdentityResolver(), transactions).enrich_nodes(caller, [node]))[0]
    assert all(projected.permissions.model_dump().values())
    assert projected.visible_to.type == "namespace"
    updated = await NodeUpdateService(VerifiedIdentityResolver(), transactions).update_node(caller, node.id, NodeChanges(name="renamed").to_core_patch(), expected_revision=node.revision)
    assert updated.visible_to == projected.visible_to
    assert updated.permissions == projected.permissions
    with pytest.raises(PermissionDenied):
        await AccessMetadataService(VerifiedIdentityResolver(), transactions).enrich_nodes(snapshot("bob", "issuer", ()), [updated])


class RevokeNamespaceAfterCommitTransactions:
    def __init__(self, transactions: FilesystemTransactions, database: Database, root_id: NodeId) -> None:
        self._transactions = transactions
        self._database = database
        self._root_id = root_id

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            yield session
        await set_shared_access(self._database, self._root_id, writable=False, discoverable=False)


@pytest.mark.asyncio
async def test_update_result_captures_commit_snapshot_and_later_projection_is_restricted(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    root = await shared_directory(database)
    caller = snapshot("alice", "issuer", ("team",))
    node = await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_file(caller, root.id, "file", root.metadata)
    transactions = create_filesystem_transactions(database=database)
    service = NodeUpdateService(VerifiedIdentityResolver(), RevokeNamespaceAfterCommitTransactions(transactions, database, root.id))
    writer = snapshot("bob", "issuer", ("team",))
    updated = await service.update_node(writer, node.id, NodeChanges(name="committed").to_core_patch(), expected_revision=node.revision)
    assert updated.name == "committed"
    assert updated.permissions.can_discover
    assert updated.visible_to.type == "namespace"
    identity = await VerifiedIdentityResolver().resolve(writer)
    async with transactions.transaction() as session:
        restricted = await project_mutation_result_access(session, identity, updated)
    assert restricted.visible_to.model_dump() == {"type": "restricted"}
    assert not any(restricted.permissions.model_dump().values())
    with pytest.raises(PermissionDenied):
        await AccessMetadataService(VerifiedIdentityResolver(), transactions).enrich_nodes(writer, [updated])


class FailingNamespaceReadTransactions:
    def __init__(self, transactions: FilesystemTransactions) -> None:
        self._transactions = transactions

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            session.access_control.list_namespace_policies = AsyncMock(side_effect=StorageFailure("Database I/O failed"))
            yield session


@pytest.mark.asyncio
async def test_namespace_io_failure_rolls_back_update(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    root = await personal_directory(database, caller)
    node = await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_file(caller, root.id, "file", root.metadata)
    transactions = FailingNamespaceReadTransactions(create_filesystem_transactions(database=database))
    with pytest.raises(StorageFailure, match="Database I/O failed"):
        await AccessMetadataService(VerifiedIdentityResolver(), transactions).enrich_nodes(caller, [node])
    with pytest.raises(StorageFailure, match="Database I/O failed"):
        await NodeUpdateService(VerifiedIdentityResolver(), transactions).update_node(caller, node.id, NodeChanges(name="not-committed").to_core_patch(), expected_revision=node.revision)
    stored = await create_namespace_driver(database=database).get_node(node.id)
    assert stored.name == node.name
    assert stored.revision == node.revision
