from pathlib import Path
from uuid import UUID, uuid4

import pytest

from umbod.core.filesystem import NodeKind, NodeMetadata, Ownership, SYSTEM_ROOT_OWNER
from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.filesystem.homes import HomeBinding
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.namespaces import CreateSharedNamespace, NamespaceGroupAccess, NamespacePolicy, SaveSharedNamespace, SaveSharedNamespaceDescription
from umbod.core.filesystem.stores.homes import DatabaseHomeTransactions
from umbod.core.filesystem.stores.namespaces import NAMESPACE_TABLE, persist_policy
from umbod.core.groups.models import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.persistence import AllFields, NoFilter, Query, TransactionMode, Unordered
from umbod.infrastructure import create_filesystem_namespaces, create_filesystem_namespace_management, create_namespace_driver
from tests.persistence_runtime import create_sqlite_runtime, prepared_sqlite_runtime
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_sqlite_reopening_retains_namespace_identity_policy_and_revision(tmp_path: Path) -> None:
    path = tmp_path / "namespaces.sqlite"
    runtime = await prepared_sqlite_runtime(path)
    caller = snapshot("alice", "issuer", ("team",))
    try:
        await create_group_management(runtime.database).register_group(RegisterGroup(group_id="team"))
        management = create_filesystem_namespace_management(database=runtime.database, issuer="issuer")
        namespace = create_namespace_driver(database=runtime.database)
        dormant = await namespace.create_node(ROOT_ID, "Shared", NodeKind.FILE, NodeMetadata(content_type="text/plain", attributes={}))
        shared = await management.create(CreateSharedNamespace(name="Shared", groups=[NamespaceGroupAccess(group_id="team", access="read_write")]))
        root = await namespace.get_node(shared.root_node_id)
        assert isinstance(root.parent_id, UUID)
        container = await namespace.get_node(root.parent_id)
        assert container.parent_id == ROOT_ID
        listing = await create_filesystem_namespaces(database=runtime.database, resolver=VerifiedIdentityResolver()).list(caller)
        saved = await management.save(shared.id, SaveSharedNamespaceDescription(name="Renamed", description="Durable description", expected_root_revision=shared.root_revision, expected_revision=1, groups=[NamespaceGroupAccess(group_id="team", access="read")]))
    finally:
        await runtime.shutdown()
    reopened = create_sqlite_runtime(path)
    try:
        await reopened.readiness.ensure_ready()
        actual = await create_filesystem_namespaces(database=reopened.database, resolver=VerifiedIdentityResolver()).list(caller)
        assert [(entry.id, entry.root_node_id) for entry in actual] == [(entry.id, entry.root_node_id) for entry in listing]
        assert actual[1].name == "Renamed"
        assert actual[1].description == saved.description == "Durable description"
        assert saved.root_revision == root.revision + 1
        assert await create_filesystem_namespace_management(database=reopened.database, issuer="issuer").list() == [saved]
        namespace = create_namespace_driver(database=reopened.database)
        renamed = await namespace.get_node(shared.root_node_id)
        assert renamed.name == "Renamed" and renamed.parent_id == container.id and renamed.revision == root.revision + 1
        assert await namespace.get_node(container.id) == container
        assert await namespace.get_node(dormant.id) == dormant
        async with reopened.database.read_session() as session:
            assert len(await session.find_many(NAMESPACE_TABLE, Query(NoFilter(), AllFields(), Unordered()))) == 2
    finally:
        await reopened.shutdown()


@pytest.mark.asyncio
async def test_sqlite_readiness_adopts_preexisting_home_without_owner_request(tmp_path: Path) -> None:
    path = tmp_path / "adoption.sqlite"
    runtime = await prepared_sqlite_runtime(path)
    owner = snapshot("alice", "issuer", ())
    identity = await VerifiedIdentityResolver().resolve(owner)
    try:
        async with DatabaseHomeTransactions(runtime.database).transaction() as session:
            await session.access_control.set_owner(Ownership(node_id=ROOT_ID, owner=SYSTEM_ROOT_OWNER))
            home = await session.namespace.create_node(ROOT_ID, "Original home", NodeKind.DIRECTORY, NodeMetadata(content_type={}, attributes={}))
            await session.access_control.set_owner(Ownership(node_id=home.id, owner=identity.user))
            await session.homes.save(HomeBinding(user=identity.user, node_id=home.id))
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        async with reopened.database.read_session() as session:
            records = await session.find_many(NAMESPACE_TABLE, Query(NoFilter(), AllFields(), Unordered()))
            assert len(records) == 1
            assert records[0].payload.root_node_id == home.id
        listed = await create_filesystem_namespaces(database=reopened.database, resolver=VerifiedIdentityResolver()).list(owner)
        assert listed[0].id == records[0].payload.id
        assert listed[0].description == ""
    finally:
        await reopened.shutdown()


@pytest.mark.asyncio
async def test_sqlite_legacy_rename_relocation_is_durable_without_changing_descendants(tmp_path: Path) -> None:
    path = tmp_path / "legacy-namespace.sqlite"
    runtime = await prepared_sqlite_runtime(path)
    metadata = NodeMetadata(content_type="text/plain", attributes={})
    try:
        async with DatabaseHomeTransactions(runtime.database).transaction() as session:
            root = await session.namespace.create_node(ROOT_ID, "Legacy", NodeKind.DIRECTORY, metadata)
            child = await session.namespace.create_node(root.id, "child", NodeKind.FILE, metadata)
            ownership = Ownership(node_id=root.id, owner=SYSTEM_ROOT_OWNER)
            await session.access_control.set_owner(ownership)
        policy = NamespacePolicy(id=uuid4(), root_node_id=root.id, name=root.name, kind="shared", issuer="issuer", revision=1, owners=frozenset(), grants=())
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await persist_policy(session, policy)
        namespace = create_namespace_driver(database=runtime.database)
        dormant = await namespace.create_node(ROOT_ID, "Occupied", NodeKind.FILE, metadata)
        saved = await create_filesystem_namespace_management(database=runtime.database, issuer="issuer").save(policy.id, SaveSharedNamespace(name="Occupied", expected_revision=1, groups=[]))
        relocated = await namespace.get_node(root.id)
        assert isinstance(relocated.parent_id, UUID) and relocated.parent_id != ROOT_ID
        container = await namespace.get_node(relocated.parent_id)
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        namespace = create_namespace_driver(database=reopened.database)
        assert await namespace.get_node(root.id) == relocated
        assert relocated.id == root.id and relocated.revision == root.revision + 1 and relocated.name == saved.name
        assert await namespace.get_node(child.id) == child
        assert await namespace.get_node(dormant.id) == dormant
        assert await namespace.get_node(container.id) == container
        assert container.parent_id == ROOT_ID
        assert await create_filesystem_namespace_management(database=reopened.database, issuer="issuer").list() == [saved]
    finally:
        await reopened.shutdown()
