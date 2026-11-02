from uuid import uuid4

import pytest

from umbod.core.filesystem import AccessGrant, NodeKind, NodeMetadata, Permission, Principal, PrincipalType, RevisionConflict
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.updates import NodeChanges, NodeUpdateService, NodePatch, Unchanged
from umbod.core.filesystem.models import MetadataPatch, UnchangedContentType, UnspecifiedContentType
from umbod.core.filesystem.namespace import ROOT_ID
from tests.umbod.core.filesystem.test_authorized_content import ContentContext, caller, stream
from tests.umbod.core.filesystem.test_authorized_content import content_context as content_context
from tests.umbod.core.filesystem.test_verified_identity import snapshot


def description_patch(description: str) -> NodePatch:
    return NodePatch(name=Unchanged(), parent_id=Unchanged(), metadata=MetadataPatch(attributes={"description": description}, content_type=UnchangedContentType()))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_description_creation_update_clear_preserves_every_other_field(
    content_context: ContentContext, kind: NodeKind,
) -> None:
    context = content_context
    metadata = NodeMetadata(content_type="text/plain", attributes={"description": "Initial", "team": "research"})
    if kind == NodeKind.FILE:
        node = await context.service.upload(caller(), ROOT_ID, "node", metadata, stream(b"bytes"))
    else:
        node = await context.creation.create_directory(caller(), ROOT_ID, "node", metadata)
    before = await context.namespace.get_node(node.id)
    service = NodeUpdateService(VerifiedIdentityResolver(), context.transactions)
    await service.check_update_eligibility(caller(), node.id)
    updated = await service.update_node(caller(), node.id, description_patch("Read for context\nnow"), expected_revision=node.revision)
    assert updated.metadata.attributes == {"description": "Read for context\nnow", "team": "research"}
    stored = await context.namespace.get_node(node.id)
    assert stored.model_dump(exclude={"metadata", "revision", "updated_at"}) == before.model_dump(exclude={"metadata", "revision", "updated_at"})
    assert stored.metadata.content_type == before.metadata.content_type
    assert stored.revision == before.revision + 1
    assert stored.updated_at >= before.updated_at
    with pytest.raises(RevisionConflict):
        await service.update_node(caller(), node.id, description_patch("stale"), expected_revision=node.revision)
    cleared = await service.update_node(caller(), node.id, description_patch(""), expected_revision=updated.revision)
    assert cleared.metadata.attributes == {"team": "research"}
    assert (await context.namespace.get_node(node.id)).metadata == cleared.metadata
    if kind == NodeKind.FILE:
        download = await context.service.open_download(caller(), node.id)
        assert b"".join([chunk async for chunk in download.data]) == b"bytes"


@pytest.mark.asyncio
@pytest.mark.parametrize("description", ["", "keep"])
@pytest.mark.parametrize("content_type", [UnchangedContentType(), "application/json", UnspecifiedContentType()])
async def test_generic_patch_preserves_omitted_attributes_and_node_structure(
    content_context: ContentContext, description: str,
    content_type: UnchangedContentType | str | UnspecifiedContentType,
) -> None:
    context = content_context
    node = await context.service.upload(
        caller(), ROOT_ID, "file", NodeMetadata(
            content_type="text/plain", attributes={"description": description, "team": "research"},
        ), stream(b"bytes"),
    )
    before = await context.namespace.get_node(node.id)
    service = NodeUpdateService(VerifiedIdentityResolver(), context.transactions)
    updated = await service.update_node(
        caller(), node.id, NodePatch(name=Unchanged(), parent_id=Unchanged(), metadata=MetadataPatch(attributes={"tag": ""}, content_type=content_type)),
        expected_revision=node.revision,
    )
    stored = await context.namespace.get_node(node.id)
    assert updated.metadata.attributes == {"description": description, "team": "research", "tag": ""}
    expected_type = "text/plain" if isinstance(content_type, UnchangedContentType) else content_type
    assert updated.metadata.content_type == expected_type
    assert stored.model_dump(exclude={"metadata", "revision", "updated_at"}) == before.model_dump(exclude={"metadata", "revision", "updated_at"})
    assert stored.revision == before.revision + 1
    assert stored.updated_at >= before.updated_at


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.WRITE}, {Permission.DISCOVER, Permission.READ}])
async def test_description_requires_discover_and_write_without_missing_node_leaks(
    content_context: ContentContext, permissions: set[Permission],
) -> None:
    context = content_context
    node = await context.creation.create_directory(caller(), ROOT_ID, "node", NodeMetadata(content_type="text/plain", attributes={}))
    bob = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    await context.policies.add_grant(AccessGrant(node_id=node.id, principal=bob, permissions=permissions, recursive=False))
    service = NodeUpdateService(VerifiedIdentityResolver(), context.transactions)
    for node_id in (node.id, uuid4()):
        with pytest.raises(PermissionDenied):
            await service.check_update_eligibility(snapshot("bob", "issuer", ()), node_id)
        with pytest.raises(PermissionDenied):
            await service.update_node(snapshot("bob", "issuer", ()), node_id, description_patch("hidden"), expected_revision=999)
    assert (await context.namespace.get_node(node.id)).revision == node.revision


@pytest.mark.asyncio
async def test_rename_direct_write_grant_needs_no_parent_access_and_rechecks_revocation(content_context: ContentContext) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), ROOT_ID, "node", NodeMetadata(content_type="text/plain", attributes={}))
    bob = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    await context.policies.add_grant(AccessGrant(node_id=node.id, principal=bob, permissions={Permission.DISCOVER, Permission.WRITE}, recursive=False))
    service = NodeUpdateService(VerifiedIdentityResolver(), context.transactions)
    actor = snapshot("bob", "issuer", ())
    await service.check_update_eligibility(actor, node.id)
    updated = await service.update_node(actor, node.id, NodeChanges(name="renamed").to_core_patch(), expected_revision=node.revision)
    assert updated.name == "renamed"
    await context.policies.remove_grant(node.id, bob)
    with pytest.raises(PermissionDenied):
        await service.update_node(actor, node.id, description_patch(""), expected_revision=updated.revision)
    with pytest.raises(PermissionDenied):
        await service.update_node(snapshot("bob", "issuer", ("",)), node.id, description_patch(""), expected_revision=updated.revision)
