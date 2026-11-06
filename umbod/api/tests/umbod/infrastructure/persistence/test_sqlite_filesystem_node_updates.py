from datetime import timedelta
from pathlib import Path

import pytest

from umbod.core.filesystem import NodeKind, NodeMetadata
from umbod.core.filesystem.namespace import initial_root, new_node
from umbod.core.filesystem.stores.namespace import node_record
from umbod.core.filesystem.stores.schema import NODE_ID, NODE_NAME, NODE_PARENT, NODE_TABLE, NodeKey
from umbod.core.persistence import AllFields, AllOf, Equals, InsertCommand, Query, TransactionMode, Unordered, UpsertCommand
from tests.persistence_runtime import prepared_sqlite_runtime


@pytest.mark.asyncio
async def test_sqlite_node_upsert_preserves_updated_indexes_and_payload_after_recreation(tmp_path: Path) -> None:
    path = tmp_path / "updates.sqlite"
    metadata = NodeMetadata(content_type="text/plain", attributes={"team": "research"})
    root = initial_root()
    destination = new_node(root.id, "destination", NodeKind.DIRECTORY, metadata)
    node = new_node(root.id, "original", NodeKind.FILE, metadata)
    updated = node_record(node.model_copy(update={
        "parent_id": destination.id, "name": "Résumé.md",
        "metadata": NodeMetadata(content_type="text/markdown", attributes={"description": "Updated"}),
        "revision": node.revision + 1, "updated_at": node.updated_at + timedelta(microseconds=1),
    }))
    runtime = await prepared_sqlite_runtime(path)
    try:
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            for original in (root, destination, node):
                assert await session.insert(NODE_TABLE, InsertCommand(row=node_record(original)))
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.upsert(NODE_TABLE, UpsertCommand(key=NodeKey(node_id=updated.node_id), row=updated))
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        async with reopened.database.read_session() as session:
            assert await session.find_one(NODE_TABLE, Query(Equals(NODE_ID, updated.node_id), AllFields(), Unordered())) == updated
            assert await session.find_many(NODE_TABLE, Query(
                AllOf((Equals(NODE_PARENT, str(root.id)), Equals(NODE_NAME, node.name))), AllFields(), Unordered(),
            )) == ()
            assert await session.find_many(NODE_TABLE, Query(
                AllOf((Equals(NODE_PARENT, str(destination.id)), Equals(NODE_NAME, updated.name))), AllFields(), Unordered(),
            )) == (updated,)
            assert await session.find_one(NODE_TABLE, Query(Equals(NODE_ID, str(root.id)), AllFields(), Unordered())) == node_record(root)
            assert await session.find_one(NODE_TABLE, Query(Equals(NODE_ID, str(destination.id)), AllFields(), Unordered())) == node_record(destination)
    finally:
        await reopened.shutdown()
