import os
import tempfile
from functools import partial
from pathlib import Path
from uuid import uuid4

from umbod.core.virtual_filesystem import ByteStream, ContentRef, StorageFailure, StorageKey

from .io import complete_io
from .objects import CHUNK_SIZE, open_regular, prepare_directory, sync_directory, validate_key


def write_chunk(descriptor: int, chunk: bytes) -> None:
    remaining = memoryview(chunk)
    while remaining:
        count = os.write(descriptor, remaining)
        if count == 0:
            raise StorageFailure("Content write made no progress")
        remaining = remaining[count:]


def publish_object(directory: Path, temporary: Path) -> StorageKey:
    while True:
        key = uuid4().hex
        try:
            os.link(temporary, directory / key, follow_symlinks=False)
        except FileExistsError:
            continue
        sync_directory(directory)
        return key


class LocalContent:
    def __init__(self, directory: Path) -> None:
        self._directory = prepare_directory(directory)

    async def put(self, data: ByteStream) -> ContentRef:
        try:
            descriptor, name = tempfile.mkstemp(prefix=".content-", dir=self._directory)
            temporary = Path(name)
            try:
                size = await self._write_stream(descriptor, data)
                await complete_io(partial(os.fsync, descriptor))
                key = await complete_io(partial(publish_object, self._directory, temporary))
                return ContentRef(key=key, size=size)
            finally:
                os.close(descriptor)
                temporary.unlink(missing_ok=True)
        except OSError as error:
            raise StorageFailure("Cannot store content object") from error

    async def _write_stream(self, descriptor: int, data: ByteStream) -> int:
        size = 0
        async for chunk in data:
            if not isinstance(chunk, bytes):
                raise StorageFailure("Content stream must yield bytes")
            for offset in range(0, len(chunk), CHUNK_SIZE):
                piece = chunk[offset:offset + CHUNK_SIZE]
                await complete_io(partial(write_chunk, descriptor, piece))
                size += len(piece)
        return size

    async def get(self, key: StorageKey) -> ByteStream:
        validate_key(key)
        try:
            descriptor = open_regular(self._directory / key, os.O_RDONLY)
            try:
                while True:
                    chunk = await complete_io(partial(os.read, descriptor, CHUNK_SIZE))
                    if not chunk:
                        break
                    yield chunk
            finally:
                os.close(descriptor)
        except OSError as error:
            raise StorageFailure("Cannot read content object") from error
