import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest

from umbod.core.filesystem import AccessGrant, NodeKind, NodeMetadata, Ownership, Permission, Principal, PrincipalType, SYSTEM_ROOT_OWNER
from umbod.core.filesystem.errors import PolicyConflict, PolicyRevisionConflict, PolicyUnavailable
from umbod.core.filesystem.authorization import AuthorizationService, PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.authorization.discovery import EffectivePermissionEvaluator
from umbod.core.filesystem.errors import InvalidMove, RootMutation
from umbod.core.filesystem.homes import HomeBinding
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.namespaces.errors import NamespaceValidationError
from umbod.core.filesystem.namespaces import CreateSharedNamespace, NamespaceGroupAccess, NamespacePolicy, SaveSharedNamespace, SharedNamespaceView
from umbod.core.filesystem.stores.discovery import DatabaseFilesystemAuthorizationReader
from umbod.core.filesystem.stores.homes import DatabaseHomeTransactions
from umbod.core.filesystem.stores.namespaces import persist_policy
from umbod.core.filesystem.updates import NodeChanges, NodeUpdateService
from umbod.core.filesystem.uploads import SystemUploadClock
from umbod.core.groups.models import GroupInUse, RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.persistence import Database, PersistenceRuntime, TransactionMode
from umbod.infrastructure import InMemoryContentConfig, create_access_control_driver, create_content_driver, create_filesystem_access, create_filesystem_browsing, create_filesystem_creation, create_filesystem_explorer, create_filesystem_namespace_management, create_filesystem_namespaces, create_filesystem_transactions, create_filesystem_uploads, create_namespace_driver
from tests.umbod.core.filesystem.test_verified_identity import snapshot


async def shared(database: Database, name: str = "Shared") -> SharedNamespaceView:
    await create_group_management(database).register_group(RegisterGroup(group_id="team"))
    return await create_filesystem_namespace_management(database=database, issuer="issuer").create(CreateSharedNamespace(name=name, groups=[NamespaceGroupAccess(group_id="team", access="read_write")]))


def metadata() -> NodeMetadata:
    return NodeMetadata(content_type="text/plain", attributes={})


@pytest.mark.asyncio
async def test_personal_listing_converges_and_is_exact_identity_scoped(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    service = create_filesystem_namespaces(database=database, resolver=VerifiedIdentityResolver())
    caller = snapshot("alice", "issuer", ())
    results = await asyncio.gather(*(service.list(caller) for _ in range(12)))
    assert all(result == results[0] for result in results)
    personal = results[0][0]
    assert personal.kind == "personal"
    assert personal.permissions == frozenset({Permission.DISCOVER, Permission.READ, Permission.WRITE, Permission.DELETE})
    other = (await service.list(snapshot("alice", "different", ())))[0]
    assert personal.id != other.id and personal.root_node_id != other.root_node_id
    assert len(await create_namespace_driver(database=database).list_children(ROOT_ID)) == 2


@pytest.mark.asyncio
async def test_existing_home_adoption_preserves_structure_and_dormant_item_sharing(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    owner = snapshot("alice", "issuer", ())
    identity = await VerifiedIdentityResolver().resolve(owner)
    async with DatabaseHomeTransactions(database).transaction() as session:
        await session.access_control.set_owner(Ownership(node_id=ROOT_ID, owner=SYSTEM_ROOT_OWNER))
        node = await session.namespace.create_node(ROOT_ID, "Existing", NodeKind.DIRECTORY, metadata())
        child = await session.namespace.create_node(node.id, "old-file", NodeKind.FILE, metadata())
        for current in (node, child):
            await session.access_control.set_owner(Ownership(node_id=current.id, owner=identity.user))
            await session.access_control.add_grant(AccessGrant(node_id=current.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"), permissions=set(Permission), recursive=True))
        await session.homes.save(HomeBinding(user=identity.user, node_id=node.id))
    browsing = create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver())
    with pytest.raises(PermissionDenied):
        await browsing.get_node(snapshot("bob", "issuer", ()), child.id)
    namespaces = await create_filesystem_namespaces(database=database, resolver=VerifiedIdentityResolver()).list(owner)
    assert namespaces[0].root_node_id == node.id
    assert (await browsing.get_node(owner, child.id)).id == child.id
    assert (await browsing.get_node(snapshot("bob", "issuer", ()), child.id)).id == child.id
    with pytest.raises(PermissionDenied):
        await browsing.get_node(snapshot("bob", "issuer", ()), node.id)


@pytest.mark.asyncio
async def test_shared_authority_adds_to_explicit_ownership_and_grants_with_exact_issuer(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    view = await shared(database)
    writer = snapshot("alice", "issuer", ("team",))
    node = await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_directory(writer, view.root_node_id, "child", metadata())
    policies = create_access_control_driver(database=database)
    await policies.add_grant(AccessGrant(node_id=node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="mallory"), permissions=set(Permission), recursive=True))
    browsing = create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver())
    for authorized in (snapshot("mallory", "issuer", ()), snapshot("alice", "issuer", ())):
        assert (await browsing.get_node(authorized, node.id)).id == node.id
    for unauthorized in (snapshot("alice", "other", ("team",)),):
        with pytest.raises(PermissionDenied):
            await browsing.get_node(unauthorized, node.id)
    enriched = (await create_filesystem_access(database=database, resolver=VerifiedIdentityResolver()).enrich_nodes(writer, [node]))[0]
    assert enriched.permissions.can_share
    assert enriched.visible_to.model_dump() == {"type": "namespace", "namespace_id": view.id, "kind": "shared", "name": view.name}
    discovery = await DatabaseFilesystemAuthorizationReader(database).read()
    identity = await VerifiedIdentityResolver().resolve(writer)
    evaluator = EffectivePermissionEvaluator(identity.principals, discovery.nodes, discovery.ownerships, discovery.grants, discovery.namespaces)
    authorization = AuthorizationService(VerifiedIdentityResolver(), create_namespace_driver(database=database), policies)
    for permission in Permission:
        assert (await authorization.decide(writer, node.id, permission)).allowed == (permission in evaluator.permissions(node.id))
    result = await create_filesystem_explorer(database=database, resolver=VerifiedIdentityResolver()).browse_node(writer, node.id)
    assert result.breadcrumbs.complete is True
    assert [item.id for item in result.breadcrumbs.items] == [view.root_node_id, node.id]
    assert str(ROOT_ID) not in result.breadcrumbs.model_dump_json()
    assert await browsing.get_breadcrumbs(writer, node.id) == result.breadcrumbs


@pytest.mark.asyncio
async def test_namespace_revocation_preserves_independent_creator_rights_and_pending_publication(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    view = await shared(database)
    writer = snapshot("alice", "issuer", ("team",))
    creation = create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver())
    node = await creation.create_directory(writer, view.root_node_id, "owned", metadata())
    uploads = create_filesystem_uploads(database=database, resolver=VerifiedIdentityResolver(), content=create_content_driver(InMemoryContentConfig(type="inmemory")), max_upload_bytes=10, clock=SystemUploadClock())
    upload = await uploads.begin(writer, node.id, "file", metadata(), 1)

    async def data() -> AsyncIterator[bytes]:
        yield b"x"

    await uploads.put(writer, upload.id, "text/plain", data())
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    await management.save(view.id, SaveSharedNamespace(expected_revision=view.revision, name=view.name, groups=[]))
    assert (await uploads.complete(writer, upload.id)).node.parent_id == node.id
    assert (await create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver()).get_node(writer, node.id)).id == node.id
    assert (await creation.create_directory(writer, node.id, "owned-child", metadata())).parent_id == node.id
    listing = await create_filesystem_namespaces(database=database, resolver=VerifiedIdentityResolver()).list(writer)
    assert len(listing) == 1 and listing[0].kind == "personal"


@pytest.mark.asyncio
async def test_root_protection_and_all_cross_boundary_moves(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    first = await shared(database, "First")
    second = await shared(database, "Second")
    caller = snapshot("alice", "issuer", ("team",))
    personal = (await create_filesystem_namespaces(database=database, resolver=VerifiedIdentityResolver()).list(caller))[0]
    updates = NodeUpdateService(VerifiedIdentityResolver(), create_filesystem_transactions(database=database))
    for root in (first.root_node_id, second.root_node_id, personal.root_node_id):
        current = await create_namespace_driver(database=database).get_node(root)
        for change in (NodeChanges(name="forbidden"), NodeChanges(parent_id=personal.root_node_id)):
            with pytest.raises(RootMutation):
                await updates.update_node(caller, root, change.to_core_patch(), expected_revision=current.revision)
    creation = create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver())
    child = await creation.create_directory(caller, first.root_node_id, "Child", metadata())
    for destination in (second.root_node_id, personal.root_node_id):
        with pytest.raises(InvalidMove):
            await updates.update_node(caller, child.id, NodeChanges(parent_id=destination).to_core_patch(), expected_revision=child.revision)
    sibling = await creation.create_directory(caller, first.root_node_id, "Sibling", metadata())
    moved = await updates.update_node(caller, child.id, NodeChanges(parent_id=sibling.id).to_core_patch(), expected_revision=child.revision)
    assert moved.parent_id == sibling.id


@pytest.mark.asyncio
async def test_management_conflicts_group_validation_and_management_is_not_content_access(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    view = await shared(database)
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    with pytest.raises(PolicyUnavailable):
        create_filesystem_namespace_management(database=database, issuer="")
    with pytest.raises(PolicyConflict):
        await management.create(CreateSharedNamespace(name=view.name, groups=[]))
    with pytest.raises(NamespaceValidationError):
        await management.create(CreateSharedNamespace(name="Unknown group", groups=[NamespaceGroupAccess(group_id="missing", access="read")]))
    with pytest.raises(GroupInUse):
        await create_group_management(database).delete_group("team")
    command = SaveSharedNamespace(expected_revision=1, name="Changed", groups=[])
    results = await asyncio.gather(management.save(view.id, command), management.save(view.id, command), return_exceptions=True)
    assert sum(isinstance(result, PolicyRevisionConflict) for result in results) == 1
    assert (await management.list())[0].revision == 2
    assert len(await create_filesystem_namespaces(database=database, resolver=VerifiedIdentityResolver()).list(snapshot("admin", "issuer", ()))) == 1


@pytest.mark.asyncio
async def test_managed_issuer_change_cannot_transfer_policy_or_reuse_revision(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    original = await shared(database)
    changed_issuer = create_filesystem_namespace_management(database=database, issuer="different")
    with pytest.raises(PolicyUnavailable):
        await changed_issuer.list()
    with pytest.raises(PolicyUnavailable):
        await changed_issuer.save(original.id, SaveSharedNamespace(expected_revision=original.revision, name="Rename", groups=[NamespaceGroupAccess(group_id="team", access="read_write")]))
    assert await create_filesystem_namespace_management(database=database, issuer="issuer").list() == [original]
    listing = await create_filesystem_namespaces(database=database, resolver=VerifiedIdentityResolver()).list(snapshot("other", "different", ("team",)))
    assert len(listing) == 1 and listing[0].kind == "personal"


@pytest.mark.asyncio
async def test_read_only_membership_disallows_mutations_sharing_and_anchor_authority(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    view = await shared(database)
    writer = snapshot("alice", "issuer", ("team",))
    node = await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_directory(writer, view.root_node_id, "child", metadata())
    await create_filesystem_namespace_management(database=database, issuer="issuer").save(view.id, SaveSharedNamespace(expected_revision=1, name=view.name, groups=[NamespaceGroupAccess(group_id="team", access="read")]))
    reader = snapshot("bob", "issuer", ("team",))
    access = (await create_filesystem_access(database=database, resolver=VerifiedIdentityResolver()).enrich_nodes(reader, [node]))[0]
    assert access.permissions.can_read is True
    assert access.permissions.can_write is access.permissions.can_delete is access.permissions.can_share is False
    with pytest.raises(PermissionDenied):
        await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_directory(reader, node.id, "denied", metadata())
    root = await create_namespace_driver(database=database).get_node(view.root_node_id)
    assert isinstance(root.parent_id, UUID)
    for ancestor_id in (ROOT_ID, root.parent_id):
        await create_access_control_driver(database=database).add_grant(AccessGrant(node_id=ancestor_id, principal=Principal(type=PrincipalType.GROUP, issuer="issuer", id="outsiders"), permissions=set(Permission), recursive=True))
    browsing = create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver())
    for caller, node_id in ((reader, ROOT_ID), (reader, root.parent_id), (snapshot("outsider", "issuer", ("outsiders",)), node.id)):
        with pytest.raises(PermissionDenied):
            await browsing.get_node(caller, node_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["file-root", "file-ancestor", "cycle-above-root", "missing-ancestor"])
async def test_namespace_projection_denies_corrupt_ancestry(filesystem_runtime: PersistenceRuntime, corruption: str) -> None:
    database = filesystem_runtime.database
    view = await shared(database)
    caller = snapshot("alice", "issuer", ("team",))
    child = await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_directory(caller, view.root_node_id, "child", metadata())
    facts = await DatabaseFilesystemAuthorizationReader(database).read()
    nodes = list(facts.nodes)
    for index, node in enumerate(nodes):
        if node.node_id == view.root_node_id and corruption == "file-root":
            nodes[index] = node.model_copy(update={"kind": NodeKind.FILE})
        if node.node_id == ROOT_ID and corruption == "file-ancestor":
            nodes[index] = node.model_copy(update={"kind": NodeKind.FILE})
        if node.node_id == ROOT_ID and corruption == "cycle-above-root":
            nodes[index] = node.model_copy(update={"parent_id": view.root_node_id})
    if corruption == "missing-ancestor":
        nodes = [node for node in nodes if node.node_id != ROOT_ID]
    identity = await VerifiedIdentityResolver().resolve(caller)
    evaluator = EffectivePermissionEvaluator(identity.principals, nodes, facts.ownerships, facts.grants, facts.namespaces)
    assert not evaluator.permissions(child.id)


@pytest.mark.asyncio
async def test_registered_personal_authority_ignores_dormant_root_ownership(filesystem_runtime: PersistenceRuntime) -> None:
    from umbod.infrastructure import create_filesystem_homes

    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    namespaces = create_filesystem_namespaces(database=database, resolver=VerifiedIdentityResolver())
    personal = (await namespaces.list(caller))[0]
    await create_access_control_driver(database=database).set_owner(Ownership(node_id=personal.root_node_id, owner=Principal(type=PrincipalType.USER, issuer="issuer", id="mallory")))
    assert (await namespaces.list(caller))[0] == personal
    assert (await create_filesystem_homes(database=database, resolver=VerifiedIdentityResolver()).get_or_provision(caller)).id == personal.root_node_id
    with pytest.raises(PermissionDenied):
        await create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver()).get_node(snapshot("mallory", "issuer", ()), personal.root_node_id)


async def legacy_shared(database: Database) -> NamespacePolicy:
    async with DatabaseHomeTransactions(database).transaction() as session:
        root = await session.namespace.create_node(ROOT_ID, "Legacy", NodeKind.DIRECTORY, metadata())
        await session.access_control.set_owner(Ownership(node_id=root.id, owner=SYSTEM_ROOT_OWNER))
    policy = NamespacePolicy(id=uuid4(), root_node_id=root.id, name=root.name, kind="shared", issuer="issuer", revision=1, owners=frozenset(), grants=())
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await persist_policy(session, policy)
    return policy


async def preserved_bytes() -> AsyncIterator[bytes]:
    yield b"original bytes"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_unmanaged_anchor_name_does_not_reserve_shared_name(filesystem_runtime: PersistenceRuntime, kind: NodeKind) -> None:
    database = filesystem_runtime.database
    namespace = create_namespace_driver(database=database)
    dormant = await namespace.create_node(ROOT_ID, "test", kind, metadata())
    file = dormant if kind == NodeKind.FILE else await namespace.create_node(dormant.id, "original", NodeKind.FILE, metadata())
    content = create_content_driver(InMemoryContentConfig(type="inmemory"))
    reference = await content.put(preserved_bytes())
    file = await namespace.update_node(file.id, content=reference, expected_revision=file.revision)
    dormant = await namespace.get_node(dormant.id)
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    created = await management.create(CreateSharedNamespace(name="test", groups=[]))
    root = await namespace.get_node(created.root_node_id)
    assert isinstance(root.parent_id, UUID)
    container = await namespace.get_node(root.parent_id)
    assert root.name == "test" and root.parent_id != ROOT_ID
    assert container.parent_id == ROOT_ID and container.name != root.name
    assert created.revision == 1 and created.groups == []
    access = create_access_control_driver(database=database)
    assert (await access.get_owner(container.id)).owner == SYSTEM_ROOT_OWNER
    assert (await access.get_owner(root.id)).owner == SYSTEM_ROOT_OWNER
    assert await access.list_grants(container.id) == []
    assert await namespace.get_node(dormant.id) == dormant
    assert await namespace.get_node(file.id) == file
    assert b"".join([chunk async for chunk in content.get(reference.key)]) == b"original bytes"
    anchors = await namespace.list_children(ROOT_ID)
    with pytest.raises(PolicyConflict):
        await management.create(CreateSharedNamespace(name="test", groups=[]))
    assert await namespace.list_children(ROOT_ID) == anchors
    browsing = create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver())
    for node_id in (ROOT_ID, container.id, root.id, dormant.id, file.id):
        with pytest.raises(PermissionDenied):
            await browsing.get_node(snapshot("admin", "issuer", ()), node_id)


@pytest.mark.asyncio
async def test_legacy_rename_relocates_only_root_and_repeated_rename_keeps_container(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    policy = await legacy_shared(database)
    namespace = create_namespace_driver(database=database)
    previous = await namespace.get_node(policy.root_node_id)
    dormant = await namespace.create_node(ROOT_ID, "Occupied", NodeKind.DIRECTORY, metadata())
    child = await namespace.create_node(previous.id, "child", NodeKind.FILE, metadata())
    content = create_content_driver(InMemoryContentConfig(type="inmemory"))
    reference = await content.put(preserved_bytes())
    child = await namespace.update_node(child.id, content=reference, expected_revision=child.revision)
    access = create_access_control_driver(database=database)
    owner = Ownership(node_id=child.id, owner=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"))
    grant = AccessGrant(node_id=child.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"), permissions={Permission.DISCOVER, Permission.READ}, recursive=False)
    await access.set_owner(owner)
    await access.add_grant(grant)
    root_grant = grant.model_copy(update={"node_id": previous.id, "recursive": True})
    await access.add_grant(root_grant)
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    renamed = await management.save(policy.id, SaveSharedNamespace(name="Occupied", expected_revision=1, groups=[]))
    root = await namespace.get_node(policy.root_node_id)
    assert renamed.id == policy.id and renamed.root_node_id == previous.id and renamed.revision == 2
    assert root.name == renamed.name and root.revision == previous.revision + 1
    assert isinstance(root.parent_id, UUID) and root.parent_id != ROOT_ID
    assert (await namespace.get_node(root.parent_id)).parent_id == ROOT_ID
    assert await namespace.get_node(dormant.id) == dormant
    assert await namespace.get_node(child.id) == child
    assert await access.get_owner(child.id) == owner
    assert await access.get_owner(root.id) == Ownership(node_id=root.id, owner=SYSTEM_ROOT_OWNER)
    assert await access.list_grants(child.id) == [grant]
    assert await access.list_grants(root.id) == [root_grant]
    assert b"".join([chunk async for chunk in content.get(reference.key)]) == b"original bytes"
    assert (await create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver()).get_node(snapshot("bob", "issuer", ()), child.id)).id == child.id
    anchors = await namespace.list_children(ROOT_ID)
    await management.save(policy.id, SaveSharedNamespace(name="Legacy", expected_revision=2, groups=[]))
    again = await namespace.get_node(root.id)
    assert again.parent_id == root.parent_id and again.revision == root.revision + 1 and again.name == "Legacy"
    assert await namespace.list_children(ROOT_ID) == anchors


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [True, False])
async def test_grant_only_save_keeps_placement_and_multiple_groups_share_root(filesystem_runtime: PersistenceRuntime, legacy: bool) -> None:
    database = filesystem_runtime.database
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    policy = await legacy_shared(database) if legacy else await management.create(CreateSharedNamespace(name="Contained", groups=[]))
    namespace = create_namespace_driver(database=database)
    root = await namespace.get_node(policy.root_node_id)
    anchors = await namespace.list_children(ROOT_ID)
    for group in ("first", "second"):
        await create_group_management(database).register_group(RegisterGroup(group_id=group))
    saved = await management.save(policy.id, SaveSharedNamespace(name=policy.name, expected_revision=1, groups=[NamespaceGroupAccess(group_id=group, access="read") for group in ("first", "second")]))
    assert saved.id == policy.id and saved.root_node_id == root.id and saved.revision == 2
    assert await namespace.get_node(root.id) == root
    assert await namespace.list_children(ROOT_ID) == anchors
    listing = create_filesystem_namespaces(database=database, resolver=VerifiedIdentityResolver())
    for group in ("first", "second"):
        namespaces = await listing.list(snapshot(group, "issuer", (group,)))
        assert [(entry.id, entry.root_node_id) for entry in namespaces if entry.kind == "shared"] == [(policy.id, root.id)]


@pytest.mark.asyncio
async def test_contained_rename_validates_actual_siblings_and_rolls_back_conflict(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    view = await shared(database)
    namespace = create_namespace_driver(database=database)
    root = await namespace.get_node(view.root_node_id)
    assert isinstance(root.parent_id, UUID)
    sibling = await namespace.create_node(root.parent_id, "Occupied", NodeKind.FILE, metadata())
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    with pytest.raises(PolicyConflict):
        await management.save(view.id, SaveSharedNamespace(name=sibling.name, expected_revision=1, groups=[]))
    assert await namespace.get_node(root.id) == root
    assert await management.list() == [view]
    await namespace.create_node(ROOT_ID, "Available", NodeKind.FILE, metadata())
    saved = await management.save(view.id, SaveSharedNamespace(name="Available", expected_revision=1, groups=[]))
    renamed = await namespace.get_node(root.id)
    assert renamed.parent_id == root.parent_id and renamed.name == saved.name


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "rename"])
async def test_container_collision_never_adopts_existing_node(filesystem_runtime: PersistenceRuntime, monkeypatch: pytest.MonkeyPatch, operation: str) -> None:
    database = filesystem_runtime.database
    policy = await legacy_shared(database) if operation == "rename" else None
    candidate = uuid4()
    namespace = create_namespace_driver(database=database)
    dormant = await namespace.create_node(ROOT_ID, str(candidate), NodeKind.DIRECTORY, metadata())
    anchors = await namespace.list_children(ROOT_ID)
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    original = await management.list()
    monkeypatch.setattr("umbod.core.filesystem.stores.namespaces.uuid4", lambda: candidate)
    with pytest.raises(PolicyConflict):
        if policy is None:
            await management.create(CreateSharedNamespace(name="New", groups=[]))
        else:
            await management.save(policy.id, SaveSharedNamespace(name="New", expected_revision=1, groups=[]))
    assert await management.list() == original
    assert await namespace.list_children(ROOT_ID) == anchors
    assert await namespace.list_children(dormant.id) == []


@pytest.mark.asyncio
async def test_failed_legacy_saves_do_not_relocate_or_change_policy(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    policy = await legacy_shared(database)
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    namespace = create_namespace_driver(database=database)
    root = await namespace.get_node(policy.root_node_id)
    for command, error in (
        (SaveSharedNamespace(name="New", expected_revision=2, groups=[]), PolicyRevisionConflict),
        (SaveSharedNamespace(name="New", expected_revision=1, groups=[NamespaceGroupAccess(group_id="missing", access="read")]), NamespaceValidationError),
    ):
        with pytest.raises(error):
            await management.save(policy.id, command)
    assert await namespace.list_children(ROOT_ID) == [root]
    assert (await management.list())[0].revision == 1

