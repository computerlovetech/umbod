from collections.abc import Sequence

from umbod.core.filesystem import (
    ContentRef,
    NamespaceDriver,
    Node,
    NodeId,
    NodeKind,
    NodeMetadata,
)


class RecordingNamespace:
    def __init__(self, namespace: NamespaceDriver) -> None:
        self._namespace = namespace
        self._creation_calls = 0
        self._roots: set[NodeId] = set()

    @property
    def creation_calls(self) -> int:
        return self._creation_calls

    @property
    def root_count(self) -> int:
        return len(self._roots)

    async def get_root(self) -> Node:
        root = await self._namespace.get_root()
        self._roots.add(root.id)
        return root

    async def get_node(self, node_id: NodeId) -> Node:
        return await self._namespace.get_node(node_id)

    async def list_children(self, parent_id: NodeId) -> Sequence[Node]:
        return await self._namespace.list_children(parent_id)

    async def create_node(
        self, parent_id: NodeId, name: str, kind: NodeKind, metadata: NodeMetadata,
    ) -> Node:
        self._creation_calls += 1
        return await self._namespace.create_node(parent_id, name, kind, metadata)

    async def update_node(
        self, node_id: NodeId, *, content: ContentRef, expected_revision: int,
    ) -> Node:
        return await self._namespace.update_node(
            node_id, content=content, expected_revision=expected_revision,
        )
