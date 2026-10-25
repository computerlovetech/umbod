import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from umbod.core.filesystem import ContentDriver, StorageFailure
from umbod.infrastructure.filesystem.local_content import LocalContent


@pytest.mark.asyncio
async def test_cancelled_content_stream_cleans_incomplete_files(tmp_path: Path) -> None:
    content: ContentDriver = LocalContent(tmp_path)

    async def cancelled() -> AsyncIterator[bytes]:
        yield b"partial"
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await content.put(cancelled())

    assert tuple(path for path in tmp_path.rglob("*") if path.is_file()) == ()


@pytest.mark.asyncio
async def test_content_symlink_cannot_expose_external_bytes(tmp_path: Path) -> None:
    directory = tmp_path / "content"
    content: ContentDriver = LocalContent(directory)
    outside = tmp_path / "outside"
    outside.write_bytes(b"private bytes")
    key = "a" * 32
    (directory / key).symlink_to(outside)

    with pytest.raises(StorageFailure):
        async for _ in content.get(key):
            pytest.fail("External bytes must not be returned")

    assert outside.read_bytes() == b"private bytes"
