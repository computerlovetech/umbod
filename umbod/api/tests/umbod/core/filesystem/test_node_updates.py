from uuid import uuid4

import pytest

from umbod.core.filesystem import AccessGrant, NodeKind, NodeMetadata, Permission, Principal, PrincipalType, RevisionConflict
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.errors import RootMutation, WrongNodeKind
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.updates import NodeChanges, NodeUpdateService
from tests.umbod.core.filesystem.test_authorized_content import ContentContext, caller, stream
from tests.umbod.core.filesystem.test_authorized_content import content_context as content_context
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_combined_update_is_atomic_and_preserves_content_and_policies(
    content_context: ContentContext, kind: NodeKind,
) -> None:
    context = content_context
    metadata = NodeMetadata(content_type="text/plain", attributes={"team": "research"})
    destination = await context.creation.create_directory(caller(), ROOT_ID, "destination", metadata)
    if kind == NodeKind.FILE:
        node = await context.service.upload(caller(), ROOT_ID, "node", metadata, stream(b"bytes"))
    else:
        node = await context.creation.create_directory(caller(), ROOT_ID, "node", metadata)
    before = await context.namespace.get_node(node.id)
    owner = await context.policies.get_owner(node.id)
    grants = await context.policies.list_grants(node.id)
    patch = NodeChanges(name="renamed", parent_id=destination.id, metadata={"attributes": {"description": "Read first"}}).to_core_patch()
    service = NodeUpdateService(VerifiedIdentityResolver(), context.transactions)
    updated = await service.update_node(caller(), node.id, patch, expected_revision=node.revision)
    assert (updated.name, updated.parent_id, updated.revision) == ("renamed", destination.id, node.revision + 1)
    assert updated.metadata.attributes == {"team": "research", "description": "Read first"}
    stored = await context.namespace.get_node(node.id)
    assert stored.content == before.content
    assert stored.created_at == before.created_at
    assert await context.policies.get_owner(node.id) == owner
    assert await context.policies.list_grants(node.id) == grants
    with pytest.raises(RevisionConflict):
        await service.update_node(caller(), node.id, NodeChanges(name="stale", parent_id=ROOT_ID).to_core_patch(), expected_revision=node.revision)
    assert await context.namespace.get_node(node.id) == stored


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["source", "destination", "item", "none"])
@pytest.mark.parametrize("permissions", [{Permission.DISCOVER}, {Permission.WRITE}, {Permission.DISCOVER, Permission.WRITE}])
async def test_move_requires_current_item_source_and_destination_grants_before_revision(
    content_context: ContentContext, missing: str, permissions: set[Permission],
) -> None:
    context = content_context
    metadata = NodeMetadata(content_type="text/plain", attributes={})
    source = await context.creation.create_directory(caller(), ROOT_ID, "source", metadata)
    destination = await context.creation.create_directory(caller(), ROOT_ID, "destination", metadata)
    node = await context.creation.create_file(caller(), source.id, "node", metadata)
    bob = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    for label, target in (("source", source), ("destination", destination), ("item", node)):
        await context.policies.add_grant(AccessGrant(
            node_id=target.id, principal=bob, recursive=False,
            permissions=permissions if label == missing else {Permission.DISCOVER, Permission.WRITE},
        ))
    service = NodeUpdateService(VerifiedIdentityResolver(), context.transactions)
    patch = NodeChanges(name="renamed", parent_id=destination.id, metadata={"attributes": {"tag": "x"}}).to_core_patch()
    expected_error = RevisionConflict if missing == "none" or permissions == {Permission.DISCOVER, Permission.WRITE} else PermissionDenied
    with pytest.raises(expected_error):
        await service.update_node(snapshot("bob", "issuer", ()), node.id, patch, expected_revision=999)
    assert (await context.namespace.get_node(node.id)).name == "node"
    assert (await context.namespace.get_node(node.id)).revision == 1
    await context.policies.remove_grant(source.id, bob)
    with pytest.raises(PermissionDenied):
        await service.update_node(snapshot("bob", "issuer", ()), node.id, patch, expected_revision=1)


@pytest.mark.asyncio
async def test_explicit_same_parent_move_requires_parent_access_and_unknown_destination_is_denied(
    content_context: ContentContext,
) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), ROOT_ID, "node", NodeMetadata(content_type="text/plain", attributes={}))
    bob = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    await context.policies.add_grant(AccessGrant(node_id=node.id, principal=bob, recursive=False, permissions={Permission.DISCOVER, Permission.WRITE}))
    service = NodeUpdateService(VerifiedIdentityResolver(), context.transactions)
    for destination in (ROOT_ID, uuid4()):
        with pytest.raises(PermissionDenied):
            await service.update_node(snapshot("bob", "issuer", ()), node.id, NodeChanges(parent_id=destination).to_core_patch(), expected_revision=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("structural", [{"name": ""}, {"parent_id": ROOT_ID}])
async def test_root_rejects_explicit_structural_change_but_allows_metadata(
    content_context: ContentContext, structural: dict[str, object],
) -> None:
    service = NodeUpdateService(VerifiedIdentityResolver(), content_context.transactions)
    root = await content_context.namespace.get_node(ROOT_ID)
    with pytest.raises(RootMutation):
        await service.update_node(caller(), ROOT_ID, NodeChanges.model_validate(structural).to_core_patch(), expected_revision=root.revision)
    updated = await service.update_node(caller(), ROOT_ID, NodeChanges(metadata={"attributes": {"description": "Root"}}).to_core_patch(), expected_revision=root.revision)
    assert updated.metadata.attributes["description"] == "Root"


@pytest.mark.asyncio
async def test_authorized_file_destination_rejects_move_without_mutation(content_context: ContentContext) -> None:
    context = content_context
    metadata = NodeMetadata(content_type="text/plain", attributes={})
    node = await context.creation.create_file(caller(), ROOT_ID, "node", metadata)
    target = await context.creation.create_file(caller(), ROOT_ID, "target", metadata)
    service = NodeUpdateService(VerifiedIdentityResolver(), context.transactions)
    with pytest.raises(WrongNodeKind):
        await service.update_node(caller(), node.id, NodeChanges(parent_id=target.id).to_core_patch(), expected_revision=1)
    assert (await context.namespace.get_node(node.id)).parent_id == ROOT_ID
