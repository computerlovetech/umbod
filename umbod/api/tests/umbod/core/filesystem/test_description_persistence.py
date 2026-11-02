from pathlib import Path

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.core.filesystem import NodeKind, NodeMetadata
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.infrastructure import create_namespace_driver


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_description_metadata_persists_after_sqlite_reopen(tmp_path: Path, kind: NodeKind) -> None:
    path = tmp_path / "descriptions.db"
    runtime = await prepared_sqlite_runtime(path)
    try:
        namespace = create_namespace_driver(database=runtime.database)
        node = await namespace.create_node(ROOT_ID, "node", kind, NodeMetadata(content_type="text/plain", attributes={"team": "research"}))
        updated = await namespace.update_metadata(
            node.id, metadata=NodeMetadata(content_type="text/plain", attributes={"team": "research", "description": "Read for context"}),
            expected_revision=node.revision,
        )
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        assert await create_namespace_driver(database=reopened.database).get_node(node.id) == updated
    finally:
        await reopened.shutdown()
