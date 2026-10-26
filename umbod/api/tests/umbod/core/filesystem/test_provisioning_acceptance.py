import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import create_autospec
from pathlib import Path

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import (
    SYSTEM_ROOT_OWNER,
    AccessControlDriver,
    FilesystemSession,
    FilesystemTransactions,
    RootProvisioning,
    RootProvisioningService,
    AccessGrant,
    NodeKind,
    Ownership,
    OwnershipNotFound,
    Permission,
    Principal,
    PrincipalType,
    ProvisioningConflict,
    RootBootstrapGrant,
    RootBootstrapSpec,
    StorageFailure,
)
from umbod.core.filesystem.authorization import (
    AuthorizationService,
    PermissionDenied,
    VerifiedIdentityResolver,
)
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    create_access_control_driver,
    create_filesystem_creation,
    create_namespace_driver,
    create_root_provisioning,
    create_filesystem_transactions,
)
from tests.persistence_runtime import prepared_sqlite_runtime
from tests.umbod.core.filesystem.test_creation_acceptance import metadata, user
from tests.umbod.core.filesystem.test_database_persistence import FailingCommitDatabase
from tests.umbod.core.filesystem.test_verified_identity import snapshot


def bootstrap_spec() -> RootBootstrapSpec:
    return RootBootstrapSpec(grants=(RootBootstrapGrant(principal=user("alice"), permissions=frozenset({Permission.DISCOVER, Permission.WRITE})),))


@pytest.mark.asyncio
async def test_clean_root_bootstrap_is_atomic_system_owned_and_direct(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    root = await create_root_provisioning(database=database).provision(bootstrap_spec())
    namespace = create_namespace_driver(database=database)
    policies = create_access_control_driver(database=database)
    assert root.id == ROOT_ID
    assert (await policies.get_owner(root.id)).owner == SYSTEM_ROOT_OWNER
    assert await policies.list_grants(root.id) == [AccessGrant(node_id=root.id, principal=user("alice"), permissions={Permission.DISCOVER, Permission.WRITE}, recursive=False)]
    authorization = AuthorizationService(VerifiedIdentityResolver(), namespace, policies)
    assert not (await authorization.decide(snapshot("alice", "issuer", ()), root.id, Permission.SHARE)).allowed


@pytest.mark.asyncio
async def test_zero_grants_and_membership_alone_confer_no_authority(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    await create_root_provisioning(database=database).provision(RootBootstrapSpec(grants=()))
    creation = create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver())
    for caller in (snapshot("alice", "issuer", ("admins",)), snapshot(SYSTEM_ROOT_OWNER.id, SYSTEM_ROOT_OWNER.issuer, ())):
        with pytest.raises(PermissionDenied):
            await creation.create_directory(caller, ROOT_ID, "denied", metadata())


@pytest.mark.asyncio
async def test_completed_bootstrap_skips_all_reconciliation_even_new_grants(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    provisioning = create_root_provisioning(database=database)
    root = await provisioning.provision(bootstrap_spec())
    policies = create_access_control_driver(database=database)
    await policies.remove_grant(ROOT_ID, user("alice"))
    bob_grant = AccessGrant(node_id=ROOT_ID, principal=user("bob"), permissions={Permission.READ}, recursive=True)
    await policies.add_grant(bob_grant)
    replacement = RootBootstrapSpec(grants=(
        RootBootstrapGrant(principal=user("alice"), permissions=frozenset(Permission)),
        RootBootstrapGrant(principal=user("new-user"), permissions=frozenset(Permission)),
    ))
    assert await provisioning.provision(replacement) == root
    assert await policies.list_grants(ROOT_ID) == [bob_grant]
    assert (await policies.get_owner(ROOT_ID)).owner == SYSTEM_ROOT_OWNER


@pytest.mark.asyncio
@pytest.mark.parametrize("dirty", ["children", "grants", "user-owner", "other-system-owner"])
async def test_legacy_or_dirty_roots_conflict_without_mutation(filesystem_runtime: PersistenceRuntime, dirty: str) -> None:
    database = filesystem_runtime.database
    namespace = create_namespace_driver(database=database)
    policies = create_access_control_driver(database=database)
    if dirty == "children":
        await namespace.create_node(ROOT_ID, "legacy", NodeKind.FILE, metadata())
    elif dirty == "grants":
        await policies.add_grant(AccessGrant(node_id=ROOT_ID, principal=user("orphan"), permissions={Permission.READ}, recursive=False))
    else:
        await policies.set_owner(Ownership(node_id=ROOT_ID, owner=user("legacy") if dirty == "user-owner" else Principal(type=PrincipalType.SYSTEM, issuer="other", id="root")))
    children = await namespace.list_children(ROOT_ID)
    grants = await policies.list_grants(ROOT_ID)
    with pytest.raises(ProvisioningConflict):
        await create_root_provisioning(database=database).provision(bootstrap_spec())
    assert await namespace.list_children(ROOT_ID) == children
    assert await policies.list_grants(ROOT_ID) == grants
    if dirty in ("children", "grants"):
        with pytest.raises(OwnershipNotFound):
            await policies.get_owner(ROOT_ID)
    else:
        assert (await policies.get_owner(ROOT_ID)).owner != SYSTEM_ROOT_OWNER


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_failed_bootstrap_can_retry_cleanly(filesystem_runtime: PersistenceRuntime, cancelled: bool) -> None:
    database = filesystem_runtime.database
    provisioning = create_root_provisioning(database=FailingCommitDatabase(database, cancelled))
    with pytest.raises(asyncio.CancelledError if cancelled else StorageFailure):
        await provisioning.provision(bootstrap_spec())
    policies = create_access_control_driver(database=database)
    with pytest.raises(OwnershipNotFound):
        await policies.get_owner(ROOT_ID)
    assert await policies.list_grants(ROOT_ID) == []
    await create_root_provisioning(database=database).provision(bootstrap_spec())
    assert (await policies.get_owner(ROOT_ID)).owner == SYSTEM_ROOT_OWNER


@pytest.mark.asyncio
async def test_concurrent_bootstrap_preserves_only_first_grant_set(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    provisioning = create_root_provisioning(database=database)
    first = bootstrap_spec()
    second = RootBootstrapSpec(grants=(RootBootstrapGrant(principal=user("bob"), permissions=frozenset({Permission.READ})),))
    roots = await asyncio.gather(provisioning.provision(first), provisioning.provision(second))
    assert roots[0] == roots[1]
    grants = await create_access_control_driver(database=database).list_grants(ROOT_ID)
    assert len(grants) == 1
    assert grants[0].principal in (user("alice"), user("bob"))


@pytest.mark.asyncio
async def test_sqlite_reopen_preserves_completion_and_does_not_regrant(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap.db"
    runtime = await prepared_sqlite_runtime(path)
    try:
        root = await create_root_provisioning(database=runtime.database).provision(bootstrap_spec())
        policies = create_access_control_driver(database=runtime.database)
        await policies.remove_grant(ROOT_ID, user("alice"))
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        assert await create_root_provisioning(database=reopened.database).provision(bootstrap_spec()) == root
        policies = create_access_control_driver(database=reopened.database)
        assert (await policies.get_owner(ROOT_ID)).owner == SYSTEM_ROOT_OWNER
        assert await policies.list_grants(ROOT_ID) == []
    finally:
        await reopened.shutdown()


def test_bootstrap_models_require_explicit_immutable_unique_user_or_group_grants() -> None:
    with pytest.raises(ValidationError):
        RootBootstrapSpec.model_validate({})
    with pytest.raises(ValidationError):
        RootBootstrapGrant.model_validate({"principal": user("alice").model_dump()})
    with pytest.raises(ValidationError):
        RootBootstrapGrant(principal=SYSTEM_ROOT_OWNER, permissions=frozenset())
    grant = RootBootstrapGrant(principal=user("alice"), permissions=frozenset({Permission.READ}))
    with pytest.raises(ValidationError):
        RootBootstrapSpec(grants=(grant, grant))
    with pytest.raises(ValidationError):
        RootBootstrapGrant.model_validate({**grant.model_dump(), "recursive": True})
    permissions = {Permission.READ}
    grants = [RootBootstrapGrant(principal=user("alice"), permissions=permissions)]
    spec = RootBootstrapSpec(grants=grants)
    permissions.clear()
    grants.clear()
    assert spec.grants[0].permissions == frozenset({Permission.READ})
    with pytest.raises(ValidationError):
        spec.grants = ()
    with pytest.raises(AttributeError):
        spec.grants[0].permissions.clear()


@pytest.mark.parametrize("issuer,identifier", [("", "alice"), (" \t", "alice"), ("issuer", ""), ("issuer", "\n ")])
def test_bootstrap_rejects_blank_principal_namespace_or_id(issuer: str, identifier: str) -> None:
    with pytest.raises(ValidationError, match="nonblank"):
        RootBootstrapGrant(principal=Principal(type=PrincipalType.USER, issuer=issuer, id=identifier), permissions=frozenset())


def test_bootstrap_preserves_exact_nonblank_principal_strings() -> None:
    principal = Principal(type=PrincipalType.GROUP, issuer=" Issuer ", id=" Team ")
    grant = RootBootstrapGrant(principal=principal, permissions=frozenset())
    assert grant.principal == principal


class FailingSecondGrantTransactions:
    def __init__(self, transactions: FilesystemTransactions, failure: BaseException) -> None:
        self._transactions = transactions
        self._failure = failure
        self.written: list[AccessGrant] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            policies = create_autospec(AccessControlDriver, instance=True)
            policies.get_owner.side_effect = session.access_control.get_owner
            policies.set_owner.side_effect = session.access_control.set_owner
            policies.list_grants.side_effect = session.access_control.list_grants

            async def add_grant(grant: AccessGrant) -> None:
                if self.written:
                    raise self._failure
                await session.access_control.add_grant(grant)
                self.written.append(grant)

            policies.add_grant.side_effect = add_grant
            yield FilesystemSession(namespace=session.namespace, access_control=policies)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_second_bootstrap_grant_failure_rolls_back_owner_and_first_grant_and_allows_retry(filesystem_runtime: PersistenceRuntime, cancelled: bool) -> None:
    database = filesystem_runtime.database
    team = Principal(type=PrincipalType.GROUP, issuer="issuer", id="team")
    spec = RootBootstrapSpec(grants=(
        RootBootstrapGrant(principal=user("alice"), permissions=frozenset({Permission.DISCOVER, Permission.WRITE})),
        RootBootstrapGrant(principal=team, permissions=frozenset({Permission.DISCOVER})),
    ))
    transactions = FailingSecondGrantTransactions(
        create_filesystem_transactions(database=database),
        asyncio.CancelledError() if cancelled else RuntimeError("second grant write failed"),
    )
    provisioning: RootProvisioning = RootProvisioningService(transactions)
    with pytest.raises(asyncio.CancelledError if cancelled else StorageFailure):
        await provisioning.provision(spec)
    assert len(transactions.written) == 1
    policies = create_access_control_driver(database=database)
    with pytest.raises(OwnershipNotFound):
        await policies.get_owner(ROOT_ID)
    assert await policies.list_grants(ROOT_ID) == []
    await create_root_provisioning(database=database).provision(spec)
    assert (await policies.get_owner(ROOT_ID)).owner == SYSTEM_ROOT_OWNER
    assert {grant.principal for grant in await policies.list_grants(ROOT_ID)} == {user("alice"), team}
