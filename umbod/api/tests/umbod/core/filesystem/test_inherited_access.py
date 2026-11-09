import pytest

from umbod.core.filesystem import AccessGrant, NodeId, NodeMetadata, Permission, Principal, PrincipalType
from umbod.core.persistence import PersistenceRuntime
from umbod.core.filesystem.access import AccessMetadataService
from umbod.core.filesystem.authorization import PermissionDenied, ResolvedIdentity, VerifiedIdentityResolver, allows_resolved, permitted_operations
from umbod.core.filesystem.authorization.discovery import FilesystemOperation
from umbod.core.filesystem.stores import DatabaseFilesystemAuthorizationReader
from umbod.core.filesystem.updates import NodeChanges, NodeUpdateService
from umbod.infrastructure import create_filesystem_explorer
from tests.umbod.core.filesystem.test_authorized_content import ContentContext, caller
from tests.umbod.core.filesystem.test_authorized_content import content_context as content_context
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from umbod.core.filesystem.namespace import ROOT_ID


def recipient(identifier: str, kind: PrincipalType = PrincipalType.USER, issuer: str = "issuer") -> Principal:
    return Principal(type=kind, issuer=issuer, id=identifier)


async def grant(context: ContentContext, node_id: NodeId, principal: Principal, permissions: set[Permission], recursive: bool) -> None:
    await context.policies.add_grant(AccessGrant(node_id=node_id, principal=principal, permissions=permissions, recursive=recursive))


@pytest.mark.asyncio
async def test_recursive_existing_and_future_descendants_union_nested_group_and_direct_permissions(content_context: ContentContext, filesystem_runtime: PersistenceRuntime) -> None:
    context = content_context
    metadata = NodeMetadata(content_type="text/plain", attributes={})
    folder = await context.creation.create_directory(caller(), ROOT_ID, "folder", metadata)
    nested = await context.creation.create_directory(caller(), folder.id, "nested", metadata)
    existing = await context.creation.create_file(caller(), nested.id, "existing", metadata)
    await grant(context, folder.id, recipient("bob"), {Permission.DISCOVER}, True)
    await grant(context, nested.id, recipient("team", PrincipalType.GROUP), {Permission.READ}, True)
    await grant(context, folder.id, recipient("bob", issuer="foreign"), {Permission.DELETE}, True)
    await grant(context, existing.id, recipient("bob"), {Permission.WRITE}, False)
    future = await context.creation.create_file(caller(), nested.id, "future", metadata)
    identity = ResolvedIdentity(user=recipient("bob"), groups={recipient("team", PrincipalType.GROUP)})
    actor = snapshot("bob", "issuer", ("team",))
    for node in (existing, future):
        assert await allows_resolved(identity, node.id, Permission.DISCOVER, context.namespace, context.policies)
        assert await allows_resolved(identity, node.id, Permission.READ, context.namespace, context.policies)
        assert not await allows_resolved(identity, node.id, Permission.DELETE, context.namespace, context.policies)
        projected = (await AccessMetadataService(VerifiedIdentityResolver(), context.transactions).enrich_nodes(actor, [node]))[0]
        assert projected.permissions.can_discover is projected.permissions.can_read is True
        assert projected.permissions.can_write is (node.id == existing.id)
        assert projected.visible_to.type == "restricted"
    explorer = create_filesystem_explorer(database=filesystem_runtime.database, resolver=VerifiedIdentityResolver(), sharing_available=True)
    result = await explorer.browse_node(actor, nested.id)
    assert {node.id for node in result.entries} == {existing.id, future.id}
    assert all(not capability.delete for capability in result.capabilities)
    projection = await DatabaseFilesystemAuthorizationReader(filesystem_runtime.database).read()
    assert {FilesystemOperation.READ, FilesystemOperation.UPDATE_METADATA}.issubset(permitted_operations(projection, identity))
    await context.policies.remove_grant(folder.id, recipient("bob"))
    assert not await allows_resolved(identity, future.id, Permission.DISCOVER, context.namespace, context.policies)
    with pytest.raises(PermissionDenied):
        await explorer.browse_node(actor, nested.id)
    assert permitted_operations(await DatabaseFilesystemAuthorizationReader(filesystem_runtime.database).read(), identity) == {FilesystemOperation.HOME}


@pytest.mark.asyncio
async def test_recursive_read_through_hidden_parent_does_not_leak_breadcrumbs(
    content_context: ContentContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    context = content_context
    metadata = NodeMetadata(content_type="text/plain", attributes={})
    hidden = await context.creation.create_directory(caller(), ROOT_ID, "hidden", metadata)
    target = await context.creation.create_file(caller(), hidden.id, "shared", metadata)
    await grant(context, ROOT_ID, recipient("bob"), {Permission.READ}, True)
    await grant(context, target.id, recipient("bob"), {Permission.DISCOVER}, False)
    actor = snapshot("bob", "issuer", ())
    result = await create_filesystem_explorer(
        database=filesystem_runtime.database, resolver=VerifiedIdentityResolver(), sharing_available=True,
    ).browse_node(actor, target.id)
    assert [item.id for item in result.breadcrumbs.items] == [target.id]
    assert result.breadcrumbs.complete is False
    assert hidden.name not in result.model_dump_json()
    projected = (await AccessMetadataService(VerifiedIdentityResolver(), context.transactions).enrich_nodes(actor, [target]))[0]
    assert projected.permissions.can_discover is projected.permissions.can_read is True
    assert projected.visible_to.type == "restricted"


@pytest.mark.asyncio
@pytest.mark.parametrize("destination_recursive", [False, True])
@pytest.mark.parametrize("preserve_direct", [False, True])
async def test_move_replaces_outer_inheritance_preserves_subtree_and_direct_grants_and_can_lose_discovery(
    content_context: ContentContext, destination_recursive: bool, preserve_direct: bool,
) -> None:
    context = content_context
    metadata = NodeMetadata(content_type="text/plain", attributes={})
    source = await context.creation.create_directory(caller(), ROOT_ID, "source", metadata)
    destination = await context.creation.create_directory(caller(), ROOT_ID, "destination", metadata)
    subtree = await context.creation.create_directory(caller(), source.id, "subtree", metadata)
    leaf = await context.creation.create_file(caller(), subtree.id, "leaf", metadata)
    await grant(context, source.id, recipient("bob"), {Permission.DISCOVER, Permission.WRITE, Permission.READ}, True)
    await grant(context, destination.id, recipient("bob"), {Permission.DISCOVER, Permission.WRITE}, destination_recursive)
    await grant(context, subtree.id, recipient("team", PrincipalType.GROUP), {Permission.READ}, True)
    await grant(context, leaf.id, recipient("reader"), {Permission.DISCOVER, Permission.DELETE}, False)
    if preserve_direct:
        await grant(context, subtree.id, recipient("bob"), {Permission.DISCOVER, Permission.SHARE}, False)
    policies_before = {node.id: await context.policies.list_grants(node.id) for node in (subtree, leaf)}
    owner_before = await context.policies.get_owner(subtree.id)
    actor = snapshot("bob", "issuer", ())
    updated = await NodeUpdateService(VerifiedIdentityResolver(), context.transactions).update_node(
        actor, subtree.id, NodeChanges(parent_id=destination.id).to_core_patch(), expected_revision=subtree.revision,
    )
    assert updated.parent_id == destination.id
    assert updated.permissions.can_discover is (destination_recursive or preserve_direct)
    assert updated.permissions.can_read is False
    assert updated.permissions.can_write is destination_recursive
    if not updated.permissions.can_discover:
        assert updated.visible_to.type == "restricted"
        with pytest.raises(PermissionDenied):
            await AccessMetadataService(VerifiedIdentityResolver(), context.transactions).enrich_nodes(actor, [updated])
    assert (await context.namespace.get_node(subtree.id)).parent_id == destination.id
    assert await context.policies.get_owner(subtree.id) == owner_before
    for node in (subtree, leaf):
        assert await context.policies.list_grants(node.id) == policies_before[node.id]
    identity = ResolvedIdentity(user=recipient("bob"), groups=frozenset())
    assert not await allows_resolved(identity, leaf.id, Permission.READ, context.namespace, context.policies)
    assert await allows_resolved(identity, leaf.id, Permission.DISCOVER, context.namespace, context.policies) is destination_recursive
    grouped = ResolvedIdentity(user=recipient("bob"), groups={recipient("team", PrincipalType.GROUP)})
    assert await allows_resolved(grouped, leaf.id, Permission.READ, context.namespace, context.policies)
    reader = ResolvedIdentity(user=recipient("reader"), groups=frozenset())
    assert await allows_resolved(reader, leaf.id, Permission.DELETE, context.namespace, context.policies)
    await NodeUpdateService(VerifiedIdentityResolver(), context.transactions).update_node(
        caller(), subtree.id, NodeChanges(parent_id=source.id).to_core_patch(), expected_revision=updated.revision,
    )
    assert await allows_resolved(identity, leaf.id, Permission.READ, context.namespace, context.policies)
