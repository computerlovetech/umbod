from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from .models import ContentRef, Node, NodeId, NodeKind, NodeMetadata, StorageKey

ByteStream = AsyncIterator[bytes]


class NamespaceDriver(Protocol):
    async def get_root(self) -> Node: ...
    async def get_node(self, node_id: NodeId) -> Node: ...
    async def list_children(self, parent_id: NodeId) -> Sequence[Node]: ...
    async def create_node(
        self, parent_id: NodeId, name: str, kind: NodeKind,
        metadata: NodeMetadata,
    ) -> Node: ...
    async def update_node(
        self, node_id: NodeId, *, content: ContentRef, expected_revision: int,
    ) -> Node: ...


class ContentDriver(Protocol):
    async def put(self, data: ByteStream) -> ContentRef: ...
    def get(self, key: StorageKey) -> ByteStream: ...
