from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem import ContentRef, WrongNodeKind
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.stores.namespaces import persist_policy
from umbod.core.persistence import TransactionMode
from umbod.infrastructure import create_filesystem_browsing
from tests.support.filesystem.namespaces import set_shared_access
from tests.umbod.core.filesystem.test_authorized_content import ContentContext, caller, metadata
from tests.umbod.core.filesystem.test_authorized_content import content_context as content_context
from tests.umbod.core.filesystem.test_effective_permissions import policy, principal
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_managed_lookup_returns_detached_safe_summaries(content_context: ContentContext) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), context.root_id, "file", metadata())
    stored = await context.namespace.update_node(node.id, content=ContentRef(key="secret-key", size=123), expected_revision=1)
    browsing = create_filesystem_browsing(database=context.database, resolver=VerifiedIdentityResolver())
    observed = await browsing.get_node(caller(), node.id)
    assert observed.model_dump() == stored.model_dump(exclude={"content"})
    assert "secret-key" not in observed.model_dump_json()
    with pytest.raises(ValidationError):
        observed.name = "changed"
    observed.metadata.attributes["custom"] = "changed"
    assert (await browsing.get_node(caller(), node.id)).metadata.attributes == {}
    assert (await context.namespace.get_node(node.id)).metadata.attributes == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
@pytest.mark.parametrize("operation", ["get_node", "list_children"])
async def test_root_and_missing_targets_are_uniformly_denied(content_context: ContentContext, missing: bool, operation: str) -> None:
    browsing = create_filesystem_browsing(database=content_context.database, resolver=VerifiedIdentityResolver())
    node_id = uuid4() if missing else ROOT_ID
    with pytest.raises(PermissionDenied, match=f"^discover denied for node {node_id}$"):
        await getattr(browsing, operation)(caller(), node_id)
    assert not hasattr(browsing, "get_root")


@pytest.mark.asyncio
async def test_listing_filters_nearest_namespace_boundary_preserving_unicode_order(content_context: ContentContext) -> None:
    context = content_context
    names = ("é", "z", "a", "é", "A")
    for name in names:
        await context.creation.create_file(caller(), context.root_id, name, metadata())
    hidden = await context.creation.create_directory(caller(), context.root_id, "hidden", metadata())
    boundary = policy(hidden.id).model_copy(update={"owners": frozenset({principal("bob")})})
    async with context.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await persist_policy(session, boundary)
    browsing = create_filesystem_browsing(database=context.database, resolver=VerifiedIdentityResolver())
    entries = await browsing.list_children(caller(), context.root_id)
    assert [node.name for node in entries] == sorted(names)
    with pytest.raises(PermissionDenied):
        await browsing.get_node(caller(), hidden.id)
    assert (await browsing.get_node(snapshot("bob", "issuer", ()), hidden.id)).id == hidden.id
    with pytest.raises(PermissionDenied):
        await browsing.list_children(snapshot("bob", "issuer", ()), context.root_id)


@pytest.mark.asyncio
async def test_file_parent_kind_is_checked_only_after_discover(content_context: ContentContext) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), context.root_id, "file", metadata())
    browsing = create_filesystem_browsing(database=context.database, resolver=VerifiedIdentityResolver())
    with pytest.raises(WrongNodeKind):
        await browsing.list_children(caller(), node.id)
    with pytest.raises(PermissionDenied):
        await browsing.list_children(snapshot("bob", "issuer", ()), node.id)


@pytest.mark.asyncio
async def test_browsing_observes_namespace_revocation_and_caller_isolation(content_context: ContentContext) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), context.root_id, "file", metadata())
    browsing = create_filesystem_browsing(database=context.database, resolver=VerifiedIdentityResolver())
    assert [entry.id for entry in await browsing.list_children(caller(), context.root_id)] == [node.id]
    with pytest.raises(PermissionDenied):
        await browsing.list_children(snapshot("bob", "issuer", ()), context.root_id)
    await set_shared_access(context.database, context.root_id, writable=False, discoverable=False)
    with pytest.raises(PermissionDenied):
        await browsing.get_node(caller(), context.root_id)
    assert (await browsing.get_node(caller(), node.id)).id == node.id
    with pytest.raises(PermissionDenied):
        await browsing.get_node(snapshot("bob", "issuer", ("team",)), node.id)
