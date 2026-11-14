import pytest

from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.access import AccessMetadataService
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver, allows_resolved, permitted_operations
from umbod.core.filesystem.authorization.discovery import FilesystemOperation
from umbod.core.filesystem.stores import DatabaseFilesystemAuthorizationReader
from umbod.core.filesystem.updates import NodeChanges, NodeUpdateService
from umbod.infrastructure import create_filesystem_explorer
from tests.support.filesystem.namespaces import set_shared_access
from tests.umbod.core.filesystem.test_authorized_content import ContentContext, caller, metadata
from tests.umbod.core.filesystem.test_authorized_content import content_context as content_context
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_namespace_authority_and_creator_rights_cover_existing_and_future_descendants(content_context: ContentContext) -> None:
    context = content_context
    folder = await context.creation.create_directory(caller(), context.root_id, "folder", metadata())
    nested = await context.creation.create_directory(caller(), folder.id, "nested", metadata())
    existing = await context.creation.create_file(caller(), nested.id, "existing", metadata())
    await context.policies.add_grant(AccessGrant(
        node_id=folder.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"), permissions=set(Permission), recursive=True,
    ))
    future = await context.creation.create_file(caller(), nested.id, "future", metadata())
    identity = await VerifiedIdentityResolver().resolve(caller())
    access = AccessMetadataService(VerifiedIdentityResolver(), context.transactions)
    for node in (existing, future):
        projected = (await access.enrich_nodes(caller(), [node]))[0]
        assert all(projected.permissions.model_dump().values())
        assert projected.visible_to.type == "namespace"
        assert await allows_resolved(identity, node.id, Permission.SHARE, context.namespace, context.policies)
    explorer = create_filesystem_explorer(database=context.database, resolver=VerifiedIdentityResolver())
    result = await explorer.browse_node(caller(), nested.id)
    assert {node.id for node in result.entries} == {existing.id, future.id}
    assert [node.id for node in result.breadcrumbs.items] == [context.root_id, folder.id, nested.id]
    assert {FilesystemOperation.READ, FilesystemOperation.UPDATE_METADATA}.issubset(permitted_operations(await DatabaseFilesystemAuthorizationReader(context.database).read(), identity))
    await set_shared_access(context.database, context.root_id, writable=False, discoverable=False)
    for node in (existing, future):
        for permission in Permission:
            assert await allows_resolved(identity, node.id, permission, context.namespace, context.policies)
    assert (await explorer.browse_node(caller(), nested.id)).node.id == nested.id
    assert FilesystemOperation.SHARE in permitted_operations(await DatabaseFilesystemAuthorizationReader(context.database).read(), identity)


@pytest.mark.asyncio
async def test_moves_within_namespace_preserve_provenance_and_independent_grants(content_context: ContentContext) -> None:
    context = content_context
    source = await context.creation.create_directory(caller(), context.root_id, "source", metadata())
    destination = await context.creation.create_directory(caller(), context.root_id, "destination", metadata())
    subtree = await context.creation.create_directory(caller(), source.id, "subtree", metadata())
    leaf = await context.creation.create_file(caller(), subtree.id, "leaf", metadata())
    outsider = Principal(type=PrincipalType.USER, issuer="issuer", id="outsider")
    for node in (source, destination, subtree, leaf):
        await context.policies.add_grant(AccessGrant(node_id=node.id, principal=outsider, permissions=set(Permission), recursive=True))
    before_grants = {node.id: await context.policies.list_grants(node.id) for node in (subtree, leaf)}
    before_owner = await context.policies.get_owner(subtree.id)
    service = NodeUpdateService(VerifiedIdentityResolver(), context.transactions)
    updated = await service.update_node(caller(), subtree.id, NodeChanges(parent_id=destination.id).to_core_patch(), expected_revision=subtree.revision)
    assert updated.parent_id == destination.id
    assert updated.permissions.can_discover and updated.permissions.can_read and updated.permissions.can_write
    assert updated.visible_to.type == "namespace"
    assert await context.policies.get_owner(subtree.id) == before_owner
    for node in (subtree, leaf):
        assert await context.policies.list_grants(node.id) == before_grants[node.id]
    identity = await VerifiedIdentityResolver().resolve(snapshot("outsider", "issuer", ()))
    for node in (subtree, leaf):
        for permission in Permission:
            assert await allows_resolved(identity, node.id, permission, context.namespace, context.policies)


@pytest.mark.asyncio
@pytest.mark.parametrize("destination_recursive", [False, True])
@pytest.mark.parametrize("preserve_direct", [False, True])
async def test_guest_move_replaces_outer_inheritance_and_can_lose_discovery(
    content_context: ContentContext, destination_recursive: bool, preserve_direct: bool,
) -> None:
    context = content_context
    source = await context.creation.create_directory(caller(), context.root_id, "source", metadata())
    destination = await context.creation.create_directory(caller(), context.root_id, "destination", metadata())
    subtree = await context.creation.create_directory(caller(), source.id, "subtree", metadata())
    leaf = await context.creation.create_file(caller(), subtree.id, "leaf", metadata())
    guest = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    await context.policies.add_grant(AccessGrant(node_id=source.id, principal=guest, permissions={Permission.DISCOVER, Permission.WRITE, Permission.READ}, recursive=True))
    await context.policies.add_grant(AccessGrant(node_id=destination.id, principal=guest, permissions={Permission.DISCOVER, Permission.WRITE}, recursive=destination_recursive))
    if preserve_direct:
        await context.policies.add_grant(AccessGrant(node_id=subtree.id, principal=guest, permissions={Permission.DISCOVER, Permission.SHARE}, recursive=False))
    actor = snapshot("bob", "issuer", ())
    updated = await NodeUpdateService(VerifiedIdentityResolver(), context.transactions).update_node(
        actor, subtree.id, NodeChanges(parent_id=destination.id).to_core_patch(), expected_revision=subtree.revision,
    )
    assert updated.permissions.can_discover == (destination_recursive or preserve_direct)
    assert not updated.permissions.can_read
    assert updated.permissions.can_write == destination_recursive
    assert updated.permissions.can_share == preserve_direct
    assert updated.visible_to.type == ("namespace" if updated.permissions.can_discover else "restricted")
    if not updated.permissions.can_discover:
        with pytest.raises(PermissionDenied):
            await AccessMetadataService(VerifiedIdentityResolver(), context.transactions).enrich_nodes(actor, [updated])
    identity = await VerifiedIdentityResolver().resolve(actor)
    assert await allows_resolved(identity, leaf.id, Permission.DISCOVER, context.namespace, context.policies) == destination_recursive
    assert not await allows_resolved(identity, leaf.id, Permission.READ, context.namespace, context.policies)
