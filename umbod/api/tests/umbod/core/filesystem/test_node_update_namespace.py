import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from umbod.core.filesystem import (
    ContentRef, InvalidMove, InvalidName, NameCollision, Node, NodeKind,
    NodeMetadata, NodeUpdate, RevisionConflict, RootMutation, WrongNodeKind,
)
from umbod.core.persistence import PersistenceRuntime
from umbod.core.messaging.stores.event_stream import DatabaseEventStream
from umbod.infrastructure import create_filesystem_transactions, create_namespace_driver
from tests.persistence_runtime import prepared_sqlite_runtime
from tests.support.filesystem.adapters import AdapterFactory, AdapterPair


def metadata() -> NodeMetadata:
    return NodeMetadata(content_type="text/plain", attributes={"team": "research"})


def details(node: Node, **changes: object) -> NodeUpdate:
    return NodeUpdate.model_validate({"name": node.name, "parent_id": node.parent_id, "metadata": node.metadata, **changes})


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_combined_update_changes_placement_and_metadata_once_preserving_identity_and_content(
    adapters: AdapterPair, kind: NodeKind,
) -> None:
    namespace = adapters.namespace
    root = await namespace.get_root()
    source = await namespace.create_node(root.id, "source", NodeKind.DIRECTORY, metadata())
    destination = await namespace.create_node(root.id, "destination", NodeKind.DIRECTORY, metadata())
    node = await namespace.create_node(source.id, "original", kind, metadata())
    if kind == NodeKind.FILE:
        node = await namespace.update_node(node.id, content=ContentRef(key=uuid4().hex, size=4), expected_revision=node.revision)
    changed = await namespace.update_details(
        node.id, details=details(node, name="renamed", parent_id=destination.id, metadata=NodeMetadata(content_type="text/markdown", attributes={"description": "Updated"})),
        expected_revision=node.revision,
    )
    assert changed.name == "renamed"
    assert changed.parent_id == destination.id
    assert changed.metadata.attributes == {"description": "Updated"}
    assert changed.metadata.content_type == "text/markdown"
    assert changed.revision == node.revision + 1
    assert changed.updated_at >= node.updated_at
    assert changed.model_dump(exclude={"name", "parent_id", "metadata", "revision", "updated_at"}) == node.model_dump(exclude={"name", "parent_id", "metadata", "revision", "updated_at"})
    assert list(await namespace.list_children(source.id)) == []
    assert list(await namespace.list_children(destination.id)) == [changed]


@pytest.mark.asyncio
async def test_moving_directory_preserves_descendant_parent_and_revision(adapters: AdapterPair) -> None:
    namespace = adapters.namespace
    root = await namespace.get_root()
    directory = await namespace.create_node(root.id, "directory", NodeKind.DIRECTORY, metadata())
    child = await namespace.create_node(directory.id, "child", NodeKind.FILE, metadata())
    destination = await namespace.create_node(root.id, "destination", NodeKind.DIRECTORY, metadata())
    await namespace.update_details(directory.id, details=details(directory, parent_id=destination.id), expected_revision=directory.revision)
    assert await namespace.get_node(child.id) == child
    assert list(await namespace.list_children(directory.id)) == [child]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["rename", "move"])
async def test_collision_rejects_every_requested_change(adapters: AdapterPair, operation: str) -> None:
    namespace = adapters.namespace
    root = await namespace.get_root()
    destination = await namespace.create_node(root.id, "destination", NodeKind.DIRECTORY, metadata())
    node = await namespace.create_node(root.id, "original", NodeKind.FILE, metadata())
    parent = root.id if operation == "rename" else destination.id
    await namespace.create_node(parent, "occupied", NodeKind.DIRECTORY, metadata())
    with pytest.raises(NameCollision):
        await namespace.update_details(
            node.id, details=details(node, name="occupied", parent_id=parent, metadata=NodeMetadata(content_type="other", attributes={})),
            expected_revision=node.revision,
        )
    assert await namespace.get_node(node.id) == node


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["self", "child", "grandchild"])
async def test_directory_cannot_move_into_itself_or_any_descendant(adapters: AdapterPair, target: str) -> None:
    namespace = adapters.namespace
    root = await namespace.get_root()
    directory = await namespace.create_node(root.id, "directory", NodeKind.DIRECTORY, metadata())
    child = await namespace.create_node(directory.id, "child", NodeKind.DIRECTORY, metadata())
    grandchild = await namespace.create_node(child.id, "grandchild", NodeKind.DIRECTORY, metadata())
    destination = {"self": directory, "child": child, "grandchild": grandchild}[target]
    with pytest.raises(InvalidMove):
        await namespace.update_details(directory.id, details=details(directory, name="changed", parent_id=destination.id), expected_revision=directory.revision)
    assert await namespace.get_node(directory.id) == directory
    assert await namespace.get_node(child.id) == child


@pytest.mark.asyncio
async def test_file_cannot_be_destination_and_rejection_does_not_rename(adapters: AdapterPair) -> None:
    namespace = adapters.namespace
    root = await namespace.get_root()
    file = await namespace.create_node(root.id, "file", NodeKind.FILE, metadata())
    node = await namespace.create_node(root.id, "node", NodeKind.FILE, metadata())
    with pytest.raises(WrongNodeKind):
        await namespace.update_details(node.id, details=details(node, name="changed", parent_id=file.id), expected_revision=node.revision)
    assert await namespace.get_node(node.id) == node


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "a\\b", "a\x00b", "\ud800"])
async def test_invalid_rename_keeps_metadata_and_revision(adapters: AdapterPair, name: str) -> None:
    namespace = adapters.namespace
    root = await namespace.get_root()
    node = await namespace.create_node(root.id, "original", NodeKind.FILE, metadata())
    with pytest.raises(InvalidName):
        await namespace.update_details(node.id, details=details(node, name=name), expected_revision=node.revision)
    assert await namespace.get_node(node.id) == node


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["rename", "move"])
async def test_root_placement_is_protected(adapters: AdapterPair, operation: str) -> None:
    root = await adapters.namespace.get_root()
    changes = {"name": "renamed"} if operation == "rename" else {"parent_id": root.id}
    with pytest.raises(RootMutation):
        await adapters.namespace.update_details(root.id, details=details(root, **changes), expected_revision=root.revision)
    assert await adapters.namespace.get_root() == root


@pytest.mark.asyncio
async def test_root_is_a_valid_move_destination(adapters: AdapterPair) -> None:
    namespace = adapters.namespace
    root = await namespace.get_root()
    folder = await namespace.create_node(root.id, "folder", NodeKind.DIRECTORY, metadata())
    node = await namespace.create_node(folder.id, "node", NodeKind.FILE, metadata())
    updated = await namespace.update_details(node.id, details=details(node, parent_id=root.id), expected_revision=node.revision)
    assert updated.parent_id == root.id


@pytest.mark.asyncio
async def test_same_placement_excludes_itself_from_collision_checks(adapters: AdapterPair) -> None:
    root = await adapters.namespace.get_root()
    node = await adapters.namespace.create_node(root.id, "original", NodeKind.FILE, metadata())
    updated = await adapters.namespace.update_details(node.id, details=details(node), expected_revision=node.revision)
    assert updated.revision == node.revision + 1
    assert updated.name == node.name


@pytest.mark.asyncio
async def test_stale_combined_change_leaves_all_fields_unchanged(adapters: AdapterPair) -> None:
    namespace = adapters.namespace
    root = await namespace.get_root()
    node = await namespace.create_node(root.id, "original", NodeKind.FILE, metadata())
    current = await namespace.update_details(node.id, details=details(node, name="first"), expected_revision=node.revision)
    with pytest.raises(RevisionConflict):
        await namespace.update_details(node.id, details=details(node, name="stale", metadata=NodeMetadata(content_type="other", attributes={})), expected_revision=node.revision)
    assert await namespace.get_node(node.id) == current


@pytest.mark.asyncio
async def test_concurrent_moves_to_same_name_have_one_winner(adapter_factory: AdapterFactory) -> None:
    namespace = adapter_factory().namespace
    root = await namespace.get_root()
    first_parent = await namespace.create_node(root.id, "first", NodeKind.DIRECTORY, metadata())
    second_parent = await namespace.create_node(root.id, "second", NodeKind.DIRECTORY, metadata())
    destination = await namespace.create_node(root.id, "destination", NodeKind.DIRECTORY, metadata())
    nodes = [await namespace.create_node(parent.id, "same", NodeKind.FILE, metadata()) for parent in (first_parent, second_parent)]
    results = await asyncio.gather(*(
        adapter_factory().namespace.update_details(node.id, details=details(node, parent_id=destination.id), expected_revision=node.revision)
        for node in nodes
    ), return_exceptions=True)
    assert sum(isinstance(result, Node) for result in results) == 1
    assert sum(isinstance(result, NameCollision) for result in results) == 1
    assert len(await namespace.list_children(destination.id)) == 1
    for node in nodes:
        stored = await namespace.get_node(node.id)
        assert stored == node or stored.parent_id == destination.id


@pytest.mark.asyncio
async def test_concurrent_updates_of_one_revision_have_one_winner(adapter_factory: AdapterFactory) -> None:
    namespace = adapter_factory().namespace
    root = await namespace.get_root()
    node = await namespace.create_node(root.id, "original", NodeKind.FILE, metadata())
    results = await asyncio.gather(*(
        adapter_factory().namespace.update_details(node.id, details=details(node, name=name), expected_revision=node.revision)
        for name in ("first", "second")
    ), return_exceptions=True)
    assert sum(isinstance(result, Node) for result in results) == 1
    assert sum(isinstance(result, RevisionConflict) for result in results) == 1


@pytest.mark.asyncio
async def test_structural_change_event_rolls_back_with_outer_transaction(filesystem_runtime: PersistenceRuntime) -> None:
    namespace = create_namespace_driver(database=filesystem_runtime.database)
    root = await namespace.get_root()
    node = await namespace.create_node(root.id, "original", NodeKind.FILE, metadata())
    events = DatabaseEventStream(filesystem_runtime.database)
    before = await events.list_after(0, 100)
    transactions = create_filesystem_transactions(database=filesystem_runtime.database)
    with pytest.raises(InvalidMove):
        async with transactions.transaction() as session:
            await session.namespace.update_details(node.id, details=details(node, name="uncommitted"), expected_revision=node.revision)
            raise InvalidMove()
    assert await namespace.get_node(node.id) == node
    assert await events.list_after(0, 100) == before
    await namespace.update_details(node.id, details=details(node, name="committed"), expected_revision=node.revision)
    after = await events.list_after(0, 100)
    assert len(after) == len(before) + 1
    assert after[-1].event.metadata == {}
    assert after[-1].event.subject == "filesystem"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_placement_and_metadata_persist_after_sqlite_reopen(tmp_path: Path, kind: NodeKind) -> None:
    path = tmp_path / "updates.db"
    runtime = await prepared_sqlite_runtime(path)
    try:
        namespace = create_namespace_driver(database=runtime.database)
        root = await namespace.get_root()
        destination = await namespace.create_node(root.id, "destination", NodeKind.DIRECTORY, metadata())
        node = await namespace.create_node(root.id, "original", kind, metadata())
        updated = await namespace.update_details(node.id, details=details(node, name="renamed", parent_id=destination.id), expected_revision=node.revision)
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        namespace = create_namespace_driver(database=reopened.database)
        assert await namespace.get_node(node.id) == updated
        assert list(await namespace.list_children(destination.id)) == [updated]
    finally:
        await reopened.shutdown()
