import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from unittest.mock import create_autospec
from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import (
    SYSTEM_ROOT_OWNER, AccessGrant, NodeKind, Ownership, Permission, Principal,
    PrincipalType, StorageFailure,
)
from umbod.core.filesystem.administration import (
    GroupPolicy, PolicyConflict, PolicyRevisionConflict, RootGroupPolicyManagement,
    RootGroupPolicyService, RootPolicySession, RootPolicyTransactions,
    SaveRootGroupPolicy,
)
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.namespace import ROOT_ID, initial_root
from umbod.core.filesystem.stores.administration import DatabaseRootPolicyTransactions
from umbod.core.filesystem.stores.schema import GRANT_TABLE, NODE_TABLE, OWNER_TABLE, NodeKey, NodeRecord
from umbod.core.persistence import AllFields, NoFilter, PersistenceRuntime, Query, TransactionMode, Unordered, UpsertCommand
from umbod.infrastructure import (
    create_access_control_driver, create_filesystem_browsing, create_filesystem_creation,
    create_namespace_driver, create_root_group_policy_management,
)
from tests.persistence_runtime import prepared_sqlite_runtime
from tests.umbod.core.filesystem.test_creation_acceptance import metadata, user
from tests.umbod.core.filesystem.test_verified_identity import snapshot


def group(identifier: str) -> GroupPolicy:
    return GroupPolicy(issuer="issuer", group_id=identifier, permissions=frozenset({Permission.DISCOVER, Permission.WRITE}))


def management(runtime: PersistenceRuntime) -> RootGroupPolicyManagement:
    return create_root_group_policy_management(database=runtime.database)


@pytest.mark.asyncio
async def test_inspect_absent_root_is_strictly_readonly(filesystem_runtime: PersistenceRuntime) -> None:
    service = management(filesystem_runtime)
    first = await service.inspect()
    assert first.status == "uninitialized"
    assert first.root_id == ROOT_ID
    assert await service.inspect() == first
    async with filesystem_runtime.database.session(mode=TransactionMode.READ_WRITE) as session:
        for table in (NODE_TABLE, OWNER_TABLE, GRANT_TABLE):
            assert not await session.find_many(table, Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()))


@pytest.mark.asyncio
async def test_unrelated_orphan_policies_do_not_affect_root_editor(filesystem_runtime: PersistenceRuntime) -> None:
    service = management(filesystem_runtime)
    initial = await service.inspect()
    policies = create_access_control_driver(database=filesystem_runtime.database)
    unrelated = uuid4()
    owner = Ownership(node_id=unrelated, owner=user("external"))
    grant = AccessGrant(node_id=unrelated, principal=user("external"), permissions={Permission.SHARE}, recursive=True)
    await policies.set_owner(owner)
    await policies.add_grant(grant)
    assert await service.inspect() == initial
    saved = await service.save(SaveRootGroupPolicy(expected_revision=initial.revision, groups=()))
    assert saved.status == "ready"
    assert await policies.get_owner(unrelated) == owner
    assert await policies.list_grants(unrelated) == [grant]


@pytest.mark.asyncio
async def test_malformed_unrelated_node_does_not_affect_root_editor(filesystem_runtime: PersistenceRuntime) -> None:
    service = management(filesystem_runtime)
    initial = await service.inspect()
    identifier, parent = uuid4(), uuid4()
    malformed = initial_root().model_copy(update={"id": identifier, "parent_id": parent, "name": ""})
    record = NodeRecord.model_construct(
        node_id=str(identifier), parent_id=str(parent), name="", revision=1, payload=malformed,
    )
    async with filesystem_runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.upsert(NODE_TABLE, UpsertCommand(key=NodeKey(node_id=str(identifier)), row=record))
    assert await service.inspect() == initial
    saved = await service.save(SaveRootGroupPolicy(expected_revision=initial.revision, groups=()))
    assert saved.status == "ready"


@pytest.mark.asyncio
async def test_malformed_root_returns_conflict_without_mutation(filesystem_runtime: PersistenceRuntime) -> None:
    malformed = initial_root().model_copy(update={"kind": NodeKind.FILE})
    record = NodeRecord.model_construct(
        node_id=str(ROOT_ID), parent_id="", name="", revision=1, payload=malformed,
    )
    async with filesystem_runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.upsert(NODE_TABLE, UpsertCommand(key=NodeKey(node_id=str(ROOT_ID)), row=record))
    service = management(filesystem_runtime)
    view = await service.inspect()
    assert view.status == "conflict"
    with pytest.raises(PolicyConflict):
        await service.save(SaveRootGroupPolicy(expected_revision=view.revision, groups=()))
    assert await service.inspect() == view


@pytest.mark.asyncio
async def test_empty_save_explicitly_initializes_without_cli(filesystem_runtime: PersistenceRuntime) -> None:
    service = management(filesystem_runtime)
    initial = await service.inspect()
    saved = await service.save(SaveRootGroupPolicy(expected_revision=initial.revision, groups=()))
    assert saved.status == "ready"
    assert saved.groups == ()
    assert saved.revision != initial.revision
    policies = create_access_control_driver(database=filesystem_runtime.database)
    assert (await policies.get_owner(ROOT_ID)).owner == SYSTEM_ROOT_OWNER


@pytest.mark.asyncio
async def test_root_group_updates_affect_authorization_and_preserve_private_children(filesystem_runtime: PersistenceRuntime) -> None:
    service = management(filesystem_runtime)
    initial = await service.inspect()
    saved = await service.save(SaveRootGroupPolicy(expected_revision=initial.revision, groups=(group("team"),)))
    database = filesystem_runtime.database
    creation = create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver())
    browsing = create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver())
    alice = snapshot("alice", "issuer", ("team",))
    bob = snapshot("bob", "issuer", ("team",))
    child = await creation.create_file(alice, ROOT_ID, "private", metadata())
    assert (await service.inspect()).revision == saved.revision
    assert await browsing.get_node(alice, child.id) == child
    with pytest.raises(PermissionDenied):
        await browsing.get_node(bob, child.id)
    await service.save(SaveRootGroupPolicy(expected_revision=saved.revision, groups=()))
    with pytest.raises(PermissionDenied):
        await browsing.get_root(alice)
    assert await browsing.get_node(alice, child.id) == child


@pytest.mark.asyncio
async def test_reconcile_direct_groups_including_raw_grants_preserves_users_and_recursive(filesystem_runtime: PersistenceRuntime) -> None:
    service = management(filesystem_runtime)
    await service.save(SaveRootGroupPolicy(expected_revision=(await service.inspect()).revision, groups=(group("old"),)))
    policies = create_access_control_driver(database=filesystem_runtime.database)
    preserved = [
        AccessGrant(node_id=ROOT_ID, principal=user("alice"), permissions={Permission.READ}, recursive=False),
        AccessGrant(node_id=ROOT_ID, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="recursive"), permissions={Permission.SHARE}, recursive=True),
    ]
    for grant in preserved:
        await policies.add_grant(grant)
    await policies.add_grant(AccessGrant(node_id=ROOT_ID, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="raw"), permissions=set(), recursive=False))
    view = await service.inspect()
    assert {item.group_id for item in view.groups} == {"old", "raw"}
    assert [item.group_id for item in view.unmanaged_groups] == ["recursive"]
    with pytest.raises(PolicyConflict):
        await service.save(SaveRootGroupPolicy(expected_revision=view.revision, groups=(group("recursive"),)))
    assert await service.inspect() == view
    await service.save(SaveRootGroupPolicy(expected_revision=view.revision, groups=()))
    assert {item.principal: item for item in await policies.list_grants(ROOT_ID)} == {item.principal: item for item in preserved}


@pytest.mark.asyncio
async def test_stale_external_raw_policy_edit_is_detected(filesystem_runtime: PersistenceRuntime) -> None:
    service = management(filesystem_runtime)
    saved = await service.save(SaveRootGroupPolicy(expected_revision=(await service.inspect()).revision, groups=()))
    policies = create_access_control_driver(database=filesystem_runtime.database)
    await policies.add_grant(AccessGrant(node_id=ROOT_ID, principal=user("alice"), permissions={Permission.READ}, recursive=False))
    with pytest.raises(PolicyRevisionConflict):
        await service.save(SaveRootGroupPolicy(expected_revision=saved.revision, groups=(group("new"),)))
    assert (await service.inspect()).groups == ()


@pytest.mark.asyncio
async def test_simultaneous_first_save_only_one_wins(filesystem_runtime: PersistenceRuntime) -> None:
    service = management(filesystem_runtime)
    initial = await service.inspect()
    results = await asyncio.gather(*(
        service.save(SaveRootGroupPolicy(expected_revision=initial.revision, groups=(group(identifier),)))
        for identifier in ("first", "second")
    ), return_exceptions=True)
    assert sum(isinstance(result, PolicyRevisionConflict) for result in results) == 1
    assert len((await service.inspect()).groups) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("dirty", ["children", "grants", "owner"])
async def test_dirty_legacy_state_conflicts_without_adoption(filesystem_runtime: PersistenceRuntime, dirty: str) -> None:
    database = filesystem_runtime.database
    policies = create_access_control_driver(database=database)
    namespace = create_namespace_driver(database=database)
    if dirty == "children":
        await namespace.create_node(ROOT_ID, "legacy", NodeKind.FILE, metadata())
    elif dirty == "owner":
        await namespace.get_root()
        await policies.set_owner(Ownership(node_id=ROOT_ID, owner=user("legacy")))
    else:
        await policies.add_grant(AccessGrant(node_id=ROOT_ID, principal=user("legacy"), permissions={Permission.READ}, recursive=False))
    service = management(filesystem_runtime)
    view = await service.inspect()
    assert view.status == "conflict"
    with pytest.raises(PolicyConflict):
        await service.save(SaveRootGroupPolicy(expected_revision=view.revision, groups=()))
    assert await service.inspect() == view


class FailingGrantTransactions:
    def __init__(self, transactions: RootPolicyTransactions, failure: BaseException) -> None:
        self._transactions = transactions
        self._failure = failure

    def read(self) -> AbstractAsyncContextManager[RootPolicySession]:
        return self._transactions.read()

    @asynccontextmanager
    async def write(self) -> AsyncIterator[RootPolicySession]:
        async with self._transactions.write() as session:
            wrapped = create_autospec(RootPolicySession, instance=True)
            wrapped.observe.side_effect = session.observe
            wrapped.ensure_root.side_effect = session.ensure_root
            wrapped.remove_group.side_effect = session.remove_group
            written = []

            async def add_group(grant: AccessGrant) -> None:
                if written:
                    raise self._failure
                await session.add_group(grant)
                written.append(grant)

            wrapped.add_group.side_effect = add_group
            yield wrapped


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_mid_grant_failure_rolls_back_root_and_all_policies(filesystem_runtime: PersistenceRuntime, cancelled: bool) -> None:
    service: RootGroupPolicyManagement = RootGroupPolicyService(FailingGrantTransactions(
        DatabaseRootPolicyTransactions(filesystem_runtime.database),
        asyncio.CancelledError() if cancelled else RuntimeError("private failure"),
    ))
    view = await service.inspect()
    with pytest.raises(asyncio.CancelledError if cancelled else StorageFailure):
        await service.save(SaveRootGroupPolicy(expected_revision=view.revision, groups=(group("first"), group("second"))))
    assert await management(filesystem_runtime).inspect() == view


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_replacement_failure_restores_exact_existing_policy_and_revision(filesystem_runtime: PersistenceRuntime, cancelled: bool) -> None:
    normal = management(filesystem_runtime)
    configured = await normal.save(SaveRootGroupPolicy(
        expected_revision=(await normal.inspect()).revision,
        groups=(group("old-first"), group("old-second")),
    ))
    policies = create_access_control_driver(database=filesystem_runtime.database)
    preserved = (
        AccessGrant(node_id=ROOT_ID, principal=user("alice"), permissions={Permission.SHARE}, recursive=False),
        AccessGrant(node_id=ROOT_ID, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="recursive"), permissions={Permission.READ}, recursive=True),
    )
    for grant in preserved:
        await policies.add_grant(grant)
    before = await normal.inspect()
    old_grants = {grant.principal: grant for grant in await policies.list_grants(ROOT_ID)}
    failing: RootGroupPolicyManagement = RootGroupPolicyService(FailingGrantTransactions(
        DatabaseRootPolicyTransactions(filesystem_runtime.database),
        asyncio.CancelledError() if cancelled else RuntimeError("replacement failed"),
    ))
    with pytest.raises(asyncio.CancelledError if cancelled else StorageFailure):
        await failing.save(SaveRootGroupPolicy(expected_revision=before.revision, groups=(group("new-first"), group("new-second"))))
    assert await normal.inspect() == before
    assert {grant.principal: grant for grant in await policies.list_grants(ROOT_ID)} == old_grants
    assert before.groups == configured.groups


@pytest.mark.asyncio
async def test_sqlite_reopen_preserves_policy_and_revision(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    runtime = await prepared_sqlite_runtime(path)
    try:
        service = management(runtime)
        saved = await service.save(SaveRootGroupPolicy(expected_revision=(await service.inspect()).revision, groups=(group("team"),)))
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        assert await management(reopened).inspect() == saved
    finally:
        await reopened.shutdown()


@pytest.mark.parametrize("payload", [
    {}, {"issuer": "", "group_id": "team", "permissions": ["read"]},
    {"issuer": "issuer", "group_id": " \t", "permissions": ["read"]},
    {"issuer": "issuer", "group_id": "team", "permissions": []},
    {"issuer": "issuer", "group_id": "team", "permissions": ["owner"]},
    {"issuer": "issuer", "group_id": "team", "permissions": ["read"], "recursive": False},
])
def test_invalid_group_policy_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GroupPolicy.model_validate(payload)


def test_policy_models_are_exact_immutable_explicit_and_unique() -> None:
    permissions = {Permission.READ}
    policy = GroupPolicy(issuer=" Issuer ", group_id=" Team ", permissions=permissions)
    permissions.clear()
    assert policy.issuer == " Issuer "
    assert policy.group_id == " Team "
    assert policy.permissions == frozenset({Permission.READ})
    with pytest.raises(ValidationError):
        policy.issuer = "changed"
    with pytest.raises(ValidationError):
        SaveRootGroupPolicy(expected_revision="revision", groups=(policy, policy))
    with pytest.raises(ValidationError):
        SaveRootGroupPolicy.model_validate({"groups": []})
    with pytest.raises(ValidationError):
        SaveRootGroupPolicy.model_validate({"expected_revision": "r", "groups": [], "owner": "admin"})
