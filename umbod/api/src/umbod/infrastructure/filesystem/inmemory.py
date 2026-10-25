from threading import RLock
from uuid import uuid4

from umbod.core.filesystem import (
    ByteStream,
    ContentRef,
    Node,
    NodeId,
    NodeKind,
    NodeMetadata,
    StorageFailure,
    StorageKey,
)
from umbod.core.filesystem.namespace import (
    ROOT_ID,
    create_node,
    get_node,
    initial_state,
    list_children,
    update_node,
)

from .objects import CHUNK_SIZE, validate_key


class InMemoryNamespace:
    def __init__(self) -> None:
        self._lock = RLock()
        self._state = initial_state()

    async def get_root(self) -> Node:
        return await self.get_node(ROOT_ID)

    async def get_node(self, node_id: NodeId) -> Node:
        with self._lock:
            return get_node(self._state, node_id)

    async def list_children(self, parent_id: NodeId) -> list[Node]:
        with self._lock:
            return list_children(self._state, parent_id)

    async def create_node(
        self, parent_id: NodeId, name: str, kind: NodeKind, metadata: NodeMetadata,
    ) -> Node:
        with self._lock:
            self._state, node = create_node(self._state, parent_id, name, kind, metadata)
            return node

    async def update_node(
        self, node_id: NodeId, *, content: ContentRef, expected_revision: int,
    ) -> Node:
        with self._lock:
            self._state, node = update_node(self._state, node_id, content, expected_revision)
            return node


class InMemoryContent:
    def __init__(self) -> None:
        self._lock = RLock()
        self._objects: dict[StorageKey, tuple[bytes, ...]] = {}

    async def put(self, data: ByteStream) -> ContentRef:
        chunks: list[bytes] = []
        size = 0
        async for chunk in data:
            if not isinstance(chunk, bytes):
                raise StorageFailure("Content stream must yield bytes")
            size += len(chunk)
            chunks.extend(chunk[offset:offset + CHUNK_SIZE] for offset in range(0, len(chunk), CHUNK_SIZE))
        with self._lock:
            key = uuid4().hex
            while key in self._objects:
                key = uuid4().hex
            self._objects[key] = tuple(chunks)
        return ContentRef(key=key, size=size)

    async def get(self, key: StorageKey) -> ByteStream:
        validate_key(key)
        with self._lock:
            try:
                chunks = self._objects[key]
            except KeyError as error:
                raise StorageFailure("Missing content object") from error
        for chunk in chunks:
            yield chunk
