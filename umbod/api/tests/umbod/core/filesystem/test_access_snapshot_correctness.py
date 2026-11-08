import pytest

from umbod.core.filesystem.access import AccessMetadataService
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.errors import StorageFailure
from umbod.core.filesystem.models import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.updates import NodeChanges, NodeUpdateService
from umbod.infrastructure import (
    create_access_control_driver, create_filesystem_browsing, create_filesystem_homes,
    create_filesystem_transactions, create_namespace_driver,
)
from tests.support.filesystem.access_snapshots import (
    FailingGrantReadTransactions, RevokeAfterCommitTransactions, fail_stored_grant_decoding,
)
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from umbod.core.persistence import PersistenceRuntime


@pytest.mark.asyncio
async def test_undecodable_policy_preserves_owner_authority_and_denies_nonowner(
    filesystem_runtime: PersistenceRuntime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    node = await create_filesystem_homes(database=database, resolver=VerifiedIdentityResolver()).get_or_provision(caller)
    grant = AccessGrant(
        node_id=node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
        permissions={Permission.DISCOVER, Permission.WRITE}, recursive=False,
    )
    policies = create_access_control_driver(database=database)
    await policies.add_grant(grant)
    fail_stored_grant_decoding(database, node.id, monkeypatch)
    transactions = create_filesystem_transactions(database=database)
    access = AccessMetadataService(VerifiedIdentityResolver(), transactions)
    projected = (await access.enrich_nodes(caller, [node]))[0]
    assert projected.permissions.model_dump() == {
        "can_discover": True, "can_read": True, "can_write": True, "can_delete": False, "can_share": True,
    }
    assert projected.visible_to.model_dump() == {"type": "unavailable"}
    assert (await create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver()).get_node(caller, node.id)).id == node.id
    with pytest.raises(PermissionDenied):
        await access.enrich_nodes(snapshot("bob", "issuer", ()), [node])
    updated = await NodeUpdateService(VerifiedIdentityResolver(), transactions).update_node(
        caller, node.id, NodeChanges(name="renamed").to_core_patch(), expected_revision=node.revision,
    )
    assert updated.name == "renamed" and updated.revision == node.revision + 1
    assert updated.visible_to.model_dump() == {"type": "unavailable"}
    assert updated.permissions == projected.permissions
    assert "permissions" not in (await create_namespace_driver(database=database).get_node(node.id)).model_dump()


@pytest.mark.asyncio
async def test_update_returns_commit_snapshot_when_direct_grant_is_revoked_after_commit(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    database = filesystem_runtime.database
    owner = snapshot("alice", "issuer", ())
    writer = snapshot("bob", "issuer", ())
    node = await create_filesystem_homes(database=database, resolver=VerifiedIdentityResolver()).get_or_provision(owner)
    principal = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    policies = create_access_control_driver(database=database)
    await policies.add_grant(AccessGrant(
        node_id=node.id, principal=principal, permissions={Permission.DISCOVER, Permission.WRITE}, recursive=False,
    ))
    transactions = create_filesystem_transactions(database=database)
    service = NodeUpdateService(
        VerifiedIdentityResolver(), RevokeAfterCommitTransactions(transactions, policies, node.id, principal),
    )
    updated = await service.update_node(
        writer, node.id, NodeChanges(name="committed").to_core_patch(), expected_revision=node.revision,
    )
    assert updated.name == "committed" and updated.revision == node.revision + 1
    assert updated.permissions.can_discover is True and updated.permissions.can_write is True
    assert updated.visible_to.model_dump() == {"type": "restricted"}
    with pytest.raises(PermissionDenied):
        await AccessMetadataService(VerifiedIdentityResolver(), transactions).enrich_nodes(writer, [updated])


@pytest.mark.asyncio
async def test_policy_io_failure_rolls_back_update_and_is_not_represented_as_unavailable(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    node = await create_filesystem_homes(database=database, resolver=VerifiedIdentityResolver()).get_or_provision(caller)
    transactions = FailingGrantReadTransactions(create_filesystem_transactions(database=database))
    access = AccessMetadataService(VerifiedIdentityResolver(), transactions)
    with pytest.raises(StorageFailure, match="Database I/O failed"):
        await access.enrich_nodes(caller, [node])
    updates = NodeUpdateService(VerifiedIdentityResolver(), transactions)
    with pytest.raises(StorageFailure, match="Database I/O failed"):
        await updates.update_node(caller, node.id, NodeChanges(name="not-committed").to_core_patch(), expected_revision=node.revision)
    stored = await create_namespace_driver(database=database).get_node(node.id)
    assert stored.name == node.name and stored.revision == node.revision
