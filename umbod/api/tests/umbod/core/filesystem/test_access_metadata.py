from uuid import uuid4

import pytest

from umbod.core.filesystem import AccessGrant, NodeKind, NodeMetadata, Ownership, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.browsing import summary
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import create_access_control_driver, create_filesystem_access, create_filesystem_creation, create_namespace_driver
from tests.support.filesystem.namespaces import personal_directory, shared_directory, set_shared_access
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_personal_metadata_exposes_namespace_without_direct_policy(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    node = await personal_directory(database, caller)
    projected = (await create_filesystem_access(database=database, resolver=VerifiedIdentityResolver()).enrich_nodes(caller, [node]))[0]
    assert projected.permissions.model_dump() == {
        "can_discover": True, "can_read": True, "can_write": True, "can_delete": False, "can_share": False,
    }
    assert projected.visible_to.type == "namespace"
    assert projected.visible_to.kind == "personal"
    assert projected.visible_to.name == "My files"
    assert set(projected.visible_to.model_dump()) == {"type", "namespace_id", "kind", "name"}
    assert "permissions" not in node.model_dump()
    assert "visible_to" not in (await create_namespace_driver(database=database).get_node(node.id)).model_dump()


@pytest.mark.asyncio
async def test_shared_metadata_preserves_independent_creator_and_direct_grant_authority(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    root = await shared_directory(database)
    caller = snapshot("alice", "issuer", ("team",))
    node = await create_filesystem_creation(database=database, resolver=VerifiedIdentityResolver()).create_file(caller, root.id, "file", NodeMetadata(content_type={}, attributes={}))
    policies = create_access_control_driver(database=database)
    await policies.add_grant(AccessGrant(node_id=node.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"), permissions=set(Permission), recursive=True))
    access = create_filesystem_access(database=database, resolver=VerifiedIdentityResolver())
    initial = (await access.enrich_nodes(caller, [node]))[0]
    assert all(initial.permissions.model_dump().values())
    assert initial.visible_to.kind == "shared"
    await set_shared_access(database, root.id, writable=False, discoverable=True)
    reader = snapshot("bob", "issuer", ("team",))
    readonly = (await access.enrich_nodes(reader, [node]))[0]
    assert readonly.permissions.can_read
    assert not readonly.permissions.can_write
    assert not readonly.permissions.can_delete
    assert readonly.visible_to == initial.visible_to
    await set_shared_access(database, root.id, writable=False, discoverable=False)
    assert (await access.enrich_nodes(caller, [node]))[0].permissions.can_share
    with pytest.raises(PermissionDenied):
        await access.enrich_nodes(reader, [node])


@pytest.mark.asyncio
async def test_unmanaged_nodes_and_missing_nodes_never_disclose_metadata(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    caller = snapshot("alice", "issuer", ())
    namespace = create_namespace_driver(database=database)
    root = await namespace.get_root()
    node = await namespace.create_node(root.id, "unmanaged", NodeKind.FILE, NodeMetadata(content_type={}, attributes={}))
    principal = Principal(type=PrincipalType.USER, issuer="issuer", id="alice")
    policies = create_access_control_driver(database=database)
    for current in (root, node):
        await policies.set_owner(Ownership(node_id=current.id, owner=principal))
        await policies.add_grant(AccessGrant(node_id=current.id, principal=principal, permissions=set(Permission), recursive=True))
    access = create_filesystem_access(database=database, resolver=VerifiedIdentityResolver())
    for current in (root, node, node.model_copy(update={"id": uuid4()})):
        with pytest.raises(PermissionDenied):
            await access.enrich_nodes(caller, [summary(current)])
