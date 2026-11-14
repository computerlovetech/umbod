from uuid import UUID

import pytest

from umbod.core.filesystem import NodeMetadata
from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.filesystem.errors import PolicyConflict, PolicyRevisionConflict, StorageFailure
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.namespaces import CreateSharedNamespace, NamespaceGroupAccess, SaveSharedNamespace, SaveSharedNamespaceDescription
from umbod.core.filesystem.namespaces.errors import NamespaceValidationError
from umbod.core.filesystem.updates import MetadataChanges, NodeChanges, NodeUpdateService
from umbod.core.persistence import DatabaseSession
from umbod.core.filesystem.namespaces import NamespacePolicy
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import create_filesystem_namespace_management, create_filesystem_namespaces, create_filesystem_transactions, create_namespace_driver
from tests.umbod.core.filesystem.test_namespaces import legacy_shared, shared
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_create_description_is_canonical_root_metadata(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    view = await management.create(CreateSharedNamespace(name="Described", description="Team reference", groups=[]))
    root = await create_namespace_driver(database=database).get_node(view.root_node_id)
    assert root.metadata.attributes == {"description": "Team reference"}
    assert view.description == "Team reference" and view.root_revision == root.revision
    assert await management.list() == [view]


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [True, False])
async def test_description_edit_and_clear_preserve_placement_and_unrelated_metadata(filesystem_runtime: PersistenceRuntime, legacy: bool) -> None:
    database = filesystem_runtime.database
    original = await legacy_shared(database) if legacy else await shared(database)
    namespace = create_namespace_driver(database=database)
    root = await namespace.get_node(original.root_node_id)
    root = await namespace.update_metadata(root.id, metadata=NodeMetadata(content_type="custom/type", attributes={"other": "retained"}), expected_revision=root.revision)
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    old = (await management.list())[0]
    assert old.description == "" and old.root_revision == root.revision
    saved = await management.save(old.id, SaveSharedNamespaceDescription(name=old.name, groups=old.groups, expected_revision=old.revision, description="New", expected_root_revision=old.root_revision))
    updated = await namespace.get_node(root.id)
    assert updated.parent_id == root.parent_id
    assert updated.metadata == NodeMetadata(content_type="custom/type", attributes={"other": "retained", "description": "New"})
    assert saved.root_revision == root.revision + 1
    omitted = await management.save(saved.id, SaveSharedNamespace(name=saved.name, groups=[], expected_revision=saved.revision))
    assert omitted.description == "New" and omitted.root_revision == saved.root_revision
    assert await namespace.get_node(root.id) == updated
    cleared = await management.save(saved.id, SaveSharedNamespaceDescription(name=saved.name, groups=[], expected_revision=omitted.revision, description="", expected_root_revision=omitted.root_revision))
    final = await namespace.get_node(root.id)
    assert final.metadata == root.metadata and final.parent_id == root.parent_id
    assert cleared.description == "" and cleared.root_revision == updated.revision + 1
    if legacy:
        assert final.parent_id == ROOT_ID


@pytest.mark.asyncio
async def test_ordinary_root_metadata_edit_invalidates_admin_revision_without_changing_policy(filesystem_runtime: PersistenceRuntime) -> None:
    database = filesystem_runtime.database
    original = await shared(database)
    caller = snapshot("alice", "issuer", ("team",))
    updates = NodeUpdateService(VerifiedIdentityResolver(), create_filesystem_transactions(database=database))
    edited = await updates.update_node(caller, original.root_node_id, NodeChanges(metadata=MetadataChanges(content_type="text/plain", attributes={"description": "Member edit", "other": "kept"})).to_core_patch(), expected_revision=original.root_revision)
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    with pytest.raises(PolicyRevisionConflict):
        await management.save(original.id, SaveSharedNamespaceDescription(name="Stale rename", groups=[], expected_revision=original.revision, description="Stale description", expected_root_revision=original.root_revision))
    current = (await management.list())[0]
    assert current.name == original.name and current.groups == original.groups and current.revision == original.revision
    assert current.description == "Member edit" and current.root_revision == edited.revision
    listed = await create_filesystem_namespaces(database=database, resolver=VerifiedIdentityResolver()).list(caller)
    assert next(entry for entry in listed if entry.id == original.id).description == current.description
    renamed = await management.save(original.id, SaveSharedNamespaceDescription(name="Combined", groups=original.groups, expected_revision=current.revision, description="Admin edit", expected_root_revision=current.root_revision))
    root = await create_namespace_driver(database=database).get_node(original.root_node_id)
    assert root.name == renamed.name and root.metadata.attributes == {"description": "Admin edit", "other": "kept"}
    assert root.revision == renamed.root_revision == edited.revision + 1


@pytest.mark.asyncio
async def test_policy_write_failure_rolls_back_combined_root_update(filesystem_runtime: PersistenceRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    database = filesystem_runtime.database
    view = await shared(database)
    namespace = create_namespace_driver(database=database)
    root = await namespace.get_node(view.root_node_id)
    management = create_filesystem_namespace_management(database=database, issuer="issuer")

    async def fail_policy_write(session: DatabaseSession, policy: NamespacePolicy) -> None:
        raise RuntimeError("Storage unavailable")

    monkeypatch.setattr("umbod.core.filesystem.stores.namespaces.persist_policy", fail_policy_write)
    with pytest.raises(StorageFailure, match="Filesystem persistence failed"):
        await management.save(view.id, SaveSharedNamespaceDescription(name="Changed", groups=[], expected_revision=view.revision, description="Changed description", expected_root_revision=view.root_revision))
    assert await management.list() == [view]
    assert await namespace.get_node(root.id) == root


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["groups", "name", "policy_revision", "root_revision"])
async def test_failed_combined_save_preserves_name_grants_description_and_revisions(filesystem_runtime: PersistenceRuntime, failure: str) -> None:
    database = filesystem_runtime.database
    view = await shared(database)
    namespace = create_namespace_driver(database=database)
    root = await namespace.get_node(view.root_node_id)
    assert isinstance(root.parent_id, UUID)
    await namespace.create_node(root.parent_id, "Occupied", root.kind, root.metadata)
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    command = SaveSharedNamespaceDescription(name="Occupied" if failure == "name" else "Changed", description="Changed description", groups=[NamespaceGroupAccess(group_id="missing", access="read")] if failure == "groups" else [], expected_revision=2 if failure == "policy_revision" else 1, expected_root_revision=root.revision + (failure == "root_revision"))
    error = NamespaceValidationError if failure == "groups" else PolicyConflict if failure == "name" else PolicyRevisionConflict
    with pytest.raises(error):
        await management.save(view.id, command)
    assert await management.list() == [view]
    assert await namespace.get_node(root.id) == root
