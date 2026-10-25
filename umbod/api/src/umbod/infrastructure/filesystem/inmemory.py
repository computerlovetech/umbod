from threading import RLock
from uuid import uuid4

from umbod.core.filesystem import (
    ByteStream,
    ContentRef,
    StorageFailure,
    StorageKey,
)
from .objects import CHUNK_SIZE, validate_key


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
            chunks.extend(
                chunk[offset : offset + CHUNK_SIZE]
                for offset in range(0, len(chunk), CHUNK_SIZE)
            )
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
