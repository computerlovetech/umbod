from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import UUID, uuid4

from umbod.core.virtual_filesystem import EmptyContent, RootParent

from .protocols import (
    ByteStream,
    ContentRefFactory,
    NodeFactory,
    PublicContentRef,
    PublicKind,
    PublicMetadata,
    PublicNode,
)


class InMemoryNamespace:
    def __init__(self, root: PublicNode, node_factory: NodeFactory) -> None:
        self._root_id = root.id
        self._nodes = {root.id: root}
        self._node_factory = node_factory
        self._creation_calls = 0

    @property
    def creation_calls(self) -> int:
        return self._creation_calls

    @property
    def root_count(self) -> int:
        return sum(isinstance(node.parent_id, RootParent) for node in self._nodes.values())

    async def get_root(self) -> PublicNode:
        return self._nodes[self._root_id]

    async def get_node(self, node_id: UUID) -> PublicNode:
        return self._nodes[node_id]

    async def get_child(self, parent_id: UUID, name: str) -> Optional[PublicNode]:
        return next(
            (node for node in self._nodes.values()
             if node.parent_id == parent_id and node.name == name),
            None,
        )

    async def list_children(self, parent_id: UUID) -> Sequence[PublicNode]:
        return tuple(sorted(
            (node for node in self._nodes.values() if node.parent_id == parent_id),
            key=lambda node: node.name,
        ))

    async def create_node(
        self, parent_id: UUID, name: str, kind: PublicKind,
        metadata: PublicMetadata,
    ) -> PublicNode:
        self._creation_calls += 1
        timestamp = datetime.now(timezone.utc)
        node = self._node_factory(
            id=uuid4(), parent_id=parent_id, name=name, kind=kind,
            metadata=metadata, content=EmptyContent(), created_at=timestamp,
            updated_at=timestamp, revision=1,
        )
        self._nodes[node.id] = node
        return node

    async def update_node(
        self, node_id: UUID, *, content: PublicContentRef, expected_revision: int,
    ) -> PublicNode:
        previous = self._nodes[node_id]
        if previous.revision != expected_revision:
            raise ValueError("Test namespace revision conflict")
        updated = self._node_factory(
            id=previous.id, parent_id=previous.parent_id, name=previous.name,
            kind=previous.kind, metadata=previous.metadata, content=content,
            created_at=previous.created_at, updated_at=datetime.now(timezone.utc),
            revision=previous.revision + 1,
        )
        self._nodes[node_id] = updated
        return updated


class InMemoryContent:
    def __init__(self, content_ref_factory: ContentRefFactory) -> None:
        self._content_ref_factory = content_ref_factory
        self._objects: dict[str, bytes] = {}

    async def put(self, data: ByteStream) -> PublicContentRef:
        stored = b"".join([chunk async for chunk in data])
        key = str(uuid4())
        self._objects[key] = stored
        return self._content_ref_factory(key=key, size=len(stored))

    async def get(self, key: str) -> ByteStream:
        data = self._objects[key]
        for offset in range(0, len(data), 7):
            yield data[offset:offset + 7]
