import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from umbod.core.callers import AuthenticationProvenance, CallerSnapshot, UnavailableSubject
from umbod.core.filesystem import (
    AccessGrant, NodeKind, NodeMetadata, NodeUpdate, Ownership, Permission, Principal, PrincipalType,
    SYSTEM_ROOT_OWNER,
)
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.provisioning import RootBootstrapSpec
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    create_access_control_driver, create_filesystem_browsing, create_filesystem_creation,
    create_filesystem_homes, create_namespace_driver, create_root_provisioning,
)
from tests.persistence_runtime import prepared_sqlite_runtime
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_home_converges_without_root_permissions_and_survives_rename(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    homes = create_filesystem_homes(database=database)
    nodes = await asyncio.gather(*(homes.get_or_provision(caller) for _ in range(8)))
    assert len({node.id for node in nodes}) == 1
    node = nodes[0]
    assert node.parent_id == ROOT_ID and node.kind == NodeKind.DIRECTORY
    assert UUID(node.name.removeprefix("Home-"))
    policies = create_access_control_driver(database=database)
    assert (await policies.get_owner(ROOT_ID)).owner == SYSTEM_ROOT_OWNER
    assert not await policies.list_grants(ROOT_ID)
    assert not await policies.list_grants(node.id)
    with pytest.raises(PermissionDenied):
        await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_directory(
            caller, ROOT_ID, "forbidden", NodeMetadata(content_type={}, attributes={}),
        )
    namespace = create_namespace_driver(database=database)
    renamed = await namespace.update_details(
        node.id, details=NodeUpdate(name="Renamed", parent_id=ROOT_ID, metadata=node.metadata),
        expected_revision=node.revision,
    )
    assert (await create_filesystem_homes(database=database).get_or_provision(caller)).name == renamed.name
    assert len(await namespace.list_children(ROOT_ID)) == 1
    await create_root_provisioning(database=database).provision(RootBootstrapSpec(grants=()))


@pytest.mark.asyncio
async def test_exact_user_issuer_home_isolation(filesystem_runtime: PersistenceRuntime) -> None:
    homes = create_filesystem_homes(database=filesystem_runtime.database)
    identities = [snapshot("alice", "issuer", ()), snapshot("alice", "other", ()),
                  snapshot("other", "issuer", ()), snapshot(" alice ", "issuer", ())]
    nodes = [await homes.get_or_provision(caller) for caller in identities]
    assert len({node.id for node in nodes}) == len(identities)
    assert [await homes.get_or_provision(caller) for caller in identities] == nodes


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", [
    AuthenticationProvenance.LOCAL_TEST, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    AuthenticationProvenance.UNAVAILABLE,
])
async def test_home_denies_unverified(
    filesystem_runtime: PersistenceRuntime, provenance: AuthenticationProvenance,
) -> None:
    caller = snapshot("alice", "issuer", ())
    caller = CallerSnapshot(caller=caller.caller.model_copy(update={
        "authentication": provenance,
        "subject": UnavailableSubject(kind="unavailable") if provenance == AuthenticationProvenance.UNAVAILABLE else caller.caller.subject,
    }), groups=caller.groups)
    with pytest.raises(PermissionDenied):
        await create_filesystem_homes(database=filesystem_runtime.database).get_or_provision(caller)


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["owner", "missing", "kind"])
async def test_home_binding_corruption_never_replaces_or_adopts(
    filesystem_runtime: PersistenceRuntime, corruption: str,
) -> None:
    from umbod.core.filesystem.homes import HomeBinding
    from umbod.core.filesystem.stores.homes import DatabaseHomeTransactions

    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    homes = create_filesystem_homes(database=database)
    if corruption == "owner":
        node = await homes.get_or_provision(caller)
        await create_access_control_driver(database=database).set_owner(Ownership(
            node_id=node.id, owner=Principal(type=PrincipalType.USER, issuer="issuer", id="mallory"),
        ))
    else:
        identity = (await VerifiedIdentityResolver().resolve(caller)).user
        async with DatabaseHomeTransactions(database).transaction() as session:
            await session.access_control.set_owner(Ownership(node_id=ROOT_ID, owner=SYSTEM_ROOT_OWNER))
            node_id = uuid4()
            if corruption == "kind":
                node = await session.namespace.create_node(
                    ROOT_ID, "not-a-home", NodeKind.FILE, NodeMetadata(content_type={}, attributes={}),
                )
                node_id = node.id
                await session.access_control.set_owner(Ownership(node_id=node_id, owner=identity))
            await session.homes.save(HomeBinding(user=identity, node_id=node_id))
    namespace = create_namespace_driver(database=database)
    before = await namespace.list_children(ROOT_ID)
    with pytest.raises(PermissionDenied):
        await homes.get_or_provision(caller)
    assert await namespace.list_children(ROOT_ID) == before


@pytest.mark.asyncio
async def test_ancestor_grants_and_admin_membership_do_not_disclose_home(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    database = filesystem_runtime.database
    home = await create_filesystem_homes(database=database).get_or_provision(snapshot("alice", "issuer", ()))
    policies = create_access_control_driver(database=database)
    await policies.add_grant(AccessGrant(
        node_id=ROOT_ID, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="administrators"),
        permissions=set(Permission), recursive=True,
    ))
    browsing = create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver())
    other = snapshot("bob", "issuer", ("administrators",))
    assert await browsing.list_children(other, ROOT_ID) == []
    with pytest.raises(PermissionDenied):
        await browsing.get_node(other, home.id)


@pytest.mark.asyncio
async def test_sqlite_reopen_retains_home_mapping(tmp_path: Path) -> None:
    path = tmp_path / "homes.sqlite"
    caller = snapshot("alice", "issuer", ())
    runtime = await prepared_sqlite_runtime(path)
    try:
        node = await create_filesystem_homes(database=runtime.database).get_or_provision(caller)
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        assert await create_filesystem_homes(database=reopened.database).get_or_provision(caller) == node
    finally:
        await reopened.shutdown()
