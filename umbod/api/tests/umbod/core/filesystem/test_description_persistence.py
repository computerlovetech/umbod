import pytest

from umbod.core.persistence import PersistenceRuntime
from umbod.core.filesystem import NodeKind, NodeMetadata
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.infrastructure import create_namespace_driver


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [NodeKind.FILE, NodeKind.DIRECTORY])
async def test_description_metadata_survives_store_recreation(
    filesystem_runtime: PersistenceRuntime, kind: NodeKind,
) -> None:
    namespace = create_namespace_driver(database=filesystem_runtime.database)
    node = await namespace.create_node(ROOT_ID, "node", kind, NodeMetadata(content_type="text/plain", attributes={"team": "research"}))
    updated = await namespace.update_metadata(
        node.id, metadata=NodeMetadata(content_type="text/plain", attributes={"team": "research", "description": "Read for context"}),
        expected_revision=node.revision,
    )
    assert await create_namespace_driver(database=filesystem_runtime.database).get_node(node.id) == updated
