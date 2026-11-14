from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import AccessGrant, Ownership, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import AuthorizationService, PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.authorization.discovery import AuthorizationGrant, EffectivePermissionEvaluator
from umbod.core.filesystem.sharing import ShareNodePolicy, GroupSharingTarget
from umbod.core.filesystem.stores import DatabaseFilesystemAuthorizationReader
from umbod.core.filesystem.stores.namespaces import persist_policy
from umbod.core.persistence import PersistenceRuntime, TransactionMode
from umbod.infrastructure import create_access_control_driver, create_filesystem_access, create_filesystem_browsing, create_filesystem_creation, create_filesystem_namespaces, create_filesystem_sharing, create_namespace_driver
from umbod.core.groups.models import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from tests.support.filesystem.namespaces import personal_directory, shared_directory, set_shared_access
from tests.umbod.core.filesystem.test_effective_permissions import policy
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_personal_child_can_be_shared_by_uuid_without_exposing_namespace_root(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    owner = snapshot("alice", "issuer", ())
    guest = snapshot("bob", "issuer", ("guests",))
    root = await personal_directory(database, owner)
    creation = create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver())
    child = await creation.create_directory(owner, root.id, "Shared folder", root.metadata)
    leaf = await creation.create_file(owner, child.id, "File", root.metadata)
    await create_group_management(database).register_group(RegisterGroup(group_id="guests"))
    sharing = create_filesystem_sharing(database=database, resolver=VerifiedIdentityResolver(), issuer="issuer")
    await sharing.share(owner, child.id, ShareNodePolicy(recipient=GroupSharingTarget(type="group", group_id="guests"), permissions=frozenset({Permission.DISCOVER, Permission.READ}), recursive=True))
    browsing = create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver())
    assert (await browsing.get_node(guest, leaf.id)).id == leaf.id
    with pytest.raises(PermissionDenied):
        await browsing.get_node(guest, root.id)
    visible_namespaces = await create_filesystem_namespaces(database=database, resolver=VerifiedIdentityResolver()).list(guest)
    assert root.id not in {namespace.root_node_id for namespace in visible_namespaces}
    access = create_filesystem_access(database=database, resolver=VerifiedIdentityResolver())
    projected = (await access.enrich_nodes(guest, [leaf]))[0]
    assert projected.visible_to.type == "namespace"
    assert projected.visible_to.kind == "personal"
    assert projected.permissions.can_read and not projected.permissions.can_share
    assert (await access.enrich_nodes(owner, [child]))[0].permissions.can_share
    assert not (await access.enrich_nodes(owner, [root]))[0].permissions.can_share
    with pytest.raises(PermissionDenied):
        await sharing.share(owner, root.id, ShareNodePolicy(recipient=GroupSharingTarget(type="group", group_id="guests"), permissions=frozenset(Permission)))
    with pytest.raises(PermissionDenied):
        await browsing.get_node(snapshot("bob", "foreign", ("guests",)), leaf.id)


@pytest.mark.asyncio
async def test_anchor_and_namespace_root_raw_acls_never_authorize_descendants(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    root = await shared_directory(database)
    creator = snapshot("alice", "issuer", ("team",))
    child = await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_directory(creator, root.id, "child", root.metadata)
    namespace = create_namespace_driver(database=database)
    anchor = await namespace.get_root()
    guest = Principal(type=PrincipalType.USER, issuer="issuer", id="guest")
    access = create_access_control_driver(database=database)
    for node in (anchor, root):
        await access.set_owner(Ownership(node_id=node.id, owner=guest))
        await access.add_grant(AccessGrant(node_id=node.id, principal=guest, permissions=set(Permission), recursive=True))
    caller = snapshot("guest", "issuer", ())
    authorization = AuthorizationService(VerifiedIdentityResolver(), namespace, access)
    facts = await DatabaseFilesystemAuthorizationReader(database).read()
    identity = await VerifiedIdentityResolver().resolve(caller)
    evaluator = EffectivePermissionEvaluator(identity.principals, facts.nodes, facts.ownerships, facts.grants, facts.namespaces)
    for node in (anchor, root, child):
        for permission in Permission:
            assert not (await authorization.decide(caller, node.id, permission)).allowed
            assert permission not in evaluator.permissions(node.id)


@pytest.mark.asyncio
async def test_nested_namespace_blocks_outer_recursive_grants_and_ownership_inheritance(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    root = await shared_directory(database)
    creator = snapshot("alice", "issuer", ("team",))
    creation = create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver())
    outer = await creation.create_directory(creator, root.id, "outer", root.metadata)
    inner = await creation.create_directory(creator, outer.id, "inner", root.metadata)
    leaf = await creation.create_file(creator, inner.id, "leaf", root.metadata)
    guest = Principal(type=PrincipalType.USER, issuer="issuer", id="guest")
    access = create_access_control_driver(database=database)
    await access.set_owner(Ownership(node_id=outer.id, owner=guest))
    await access.add_grant(AccessGrant(node_id=outer.id, principal=guest, permissions=set(Permission), recursive=True))
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await persist_policy(session, policy(inner.id))
    browsing = create_filesystem_browsing(database=database, resolver=VerifiedIdentityResolver())
    caller = snapshot("guest", "issuer", ())
    assert (await browsing.get_node(caller, outer.id)).id == outer.id
    for node in (inner, leaf):
        with pytest.raises(PermissionDenied):
            await browsing.get_node(caller, node.id)
    await access.add_grant(AccessGrant(node_id=leaf.id, principal=guest, permissions={Permission.DISCOVER}, recursive=False))
    assert (await browsing.get_node(caller, leaf.id)).id == leaf.id
    with pytest.raises(PermissionDenied):
        await browsing.get_node(caller, inner.id)


@pytest.mark.asyncio
async def test_group_baseline_and_direct_grants_are_additive_and_non_subtractive(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    root = await shared_directory(database)
    creator = snapshot("alice", "issuer", ("team",))
    child = await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_file(creator, root.id, "child", root.metadata)
    guest = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    access = create_access_control_driver(database=database)
    await set_shared_access(database, root.id, writable=False, discoverable=True)
    await access.add_grant(AccessGrant(node_id=child.id, principal=guest, permissions={Permission.WRITE}, recursive=False))
    caller = snapshot("bob", "issuer", ("team",))
    metadata = create_filesystem_access(database=database, resolver=VerifiedIdentityResolver())
    initial = (await metadata.enrich_nodes(caller, [child]))[0]
    assert initial.permissions.can_read and initial.permissions.can_write and not initial.permissions.can_share
    await access.add_grant(AccessGrant(node_id=child.id, principal=guest, permissions=set(), recursive=False))
    reduced = (await metadata.enrich_nodes(caller, [child]))[0]
    assert reduced.permissions.can_read and not reduced.permissions.can_write
    await access.add_grant(AccessGrant(node_id=child.id, principal=guest, permissions={Permission.DISCOVER, Permission.WRITE}, recursive=False))
    await set_shared_access(database, root.id, writable=False, discoverable=False)
    explicit = (await metadata.enrich_nodes(caller, [child]))[0]
    assert explicit.permissions.can_write and not explicit.permissions.can_read
    await access.remove_grant(child.id, guest)
    with pytest.raises(PermissionDenied):
        await metadata.enrich_nodes(caller, [child])


def test_authorization_grants_freeze_and_detach_permission_inputs() -> None:
    permissions = {Permission.DISCOVER, Permission.SHARE}
    grant = AuthorizationGrant(node_id=uuid4(), principal=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"), permissions=permissions, recursive=True)
    permissions.clear()
    assert grant.permissions == {Permission.DISCOVER, Permission.SHARE}
    with pytest.raises(ValidationError):
        grant.recursive = False
    with pytest.raises(AttributeError):
        grant.permissions.clear()
