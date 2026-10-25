import asyncio
from collections.abc import AsyncIterator

import pytest

from umbod.core.virtual_filesystem import (
    Node,
    NodeKind,
    NodeMetadata,
    RevisionConflict,
    StorageFailure,
    UnspecifiedContentType,
    VirtualFilesystem,
    WrongNodeKind,
)

from tests.support.virtual_filesystem.adapters import AdapterFactory, AdapterPair


async def stream(data: bytes) -> AsyncIterator[bytes]:
    for offset in range(0, len(data), 113):
        yield data[offset:offset + 113]


async def collect(chunks: AsyncIterator[bytes]) -> bytes:
    return b"".join([chunk async for chunk in chunks])


async def create_file(adapters: AdapterPair) -> Node:
    root = await adapters.namespace.get_root()
    return await adapters.namespace.create_node(
        root.id, "payload", NodeKind.FILE,
        NodeMetadata(content_type=UnspecifiedContentType(), attributes={}),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [b"", bytes(range(256)) * 4096])
async def test_complete_content_is_readable_with_exact_size(adapters: AdapterPair, data: bytes) -> None:
    reference = await adapters.content.put(stream(data))

    assert reference.size == len(data)
    assert await collect(adapters.content.get(reference.key)) == data


@pytest.mark.asyncio
async def test_content_objects_are_independent_and_immutable(adapters: AdapterPair) -> None:
    first = await adapters.content.put(stream(b"first"))
    second = await adapters.content.put(stream(b"second"))

    assert first.key != second.key
    assert await collect(adapters.content.get(first.key)) == b"first"
    assert await collect(adapters.content.get(second.key)) == b"second"


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["../escape", "/absolute", "", "not-a-key", "a" * 32])
async def test_invalid_or_missing_content_keys_fail_safely(adapters: AdapterPair, key: str) -> None:
    with pytest.raises(StorageFailure):
        await collect(adapters.content.get(key))


@pytest.mark.asyncio
async def test_failed_input_stream_does_not_publish_file_content(adapters: AdapterPair) -> None:
    file = await create_file(adapters)
    filesystem = VirtualFilesystem(namespace=adapters.namespace, content=adapters.content)
    previous = await filesystem.write(file.id, stream(b"previous"), expected_revision=file.revision)

    async def interrupted() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("input failed")

    with pytest.raises(RuntimeError, match="input failed"):
        await filesystem.write(file.id, interrupted(), expected_revision=previous.revision)

    assert await adapters.namespace.get_node(file.id) == previous
    assert await collect(filesystem.read(file.id)) == b"previous"


@pytest.mark.asyncio
async def test_cancelled_input_stream_preserves_file_content(adapters: AdapterPair) -> None:
    file = await create_file(adapters)
    filesystem = VirtualFilesystem(namespace=adapters.namespace, content=adapters.content)

    async def cancelled() -> AsyncIterator[bytes]:
        yield b"partial"
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await filesystem.write(file.id, cancelled(), expected_revision=file.revision)

    assert await adapters.namespace.get_node(file.id) == file
    assert await collect(filesystem.read(file.id)) == b""


@pytest.mark.asyncio
async def test_replacing_content_keeps_old_objects_readable(adapters: AdapterPair) -> None:
    file = await create_file(adapters)
    old = await adapters.content.put(stream(b"old bytes"))
    published = await adapters.namespace.update_node(file.id, content=old, expected_revision=file.revision)
    filesystem = VirtualFilesystem(namespace=adapters.namespace, content=adapters.content)

    await filesystem.write(file.id, stream(b"new bytes"), expected_revision=published.revision)

    assert await collect(filesystem.read(file.id)) == b"new bytes"
    assert await collect(adapters.content.get(old.key)) == b"old bytes"


@pytest.mark.asyncio
async def test_competing_writes_have_one_revision_winner(adapter_factory: AdapterFactory) -> None:
    first_pair = adapter_factory()
    second_pair = adapter_factory()
    file = await create_file(first_pair)
    first = VirtualFilesystem(namespace=first_pair.namespace, content=first_pair.content)
    second = VirtualFilesystem(namespace=second_pair.namespace, content=second_pair.content)

    results = await asyncio.gather(
        first.write(file.id, stream(b"first"), expected_revision=file.revision),
        second.write(file.id, stream(b"second"), expected_revision=file.revision),
        return_exceptions=True,
    )

    assert sum(isinstance(result, Node) for result in results) == 1
    assert sum(isinstance(result, RevisionConflict) for result in results) == 1
    assert await collect(first.read(file.id)) in (b"first", b"second")
    assert (await first.get_node(file.id)).revision == file.revision + 1


@pytest.mark.asyncio
async def test_directory_content_operations_are_rejected_before_consuming_input(adapters: AdapterPair) -> None:
    root = await adapters.namespace.get_root()
    filesystem = VirtualFilesystem(namespace=adapters.namespace, content=adapters.content)
    consumed: list[bytes] = []

    async def observed() -> AsyncIterator[bytes]:
        consumed.append(b"payload")
        yield b"payload"

    with pytest.raises(WrongNodeKind):
        await filesystem.write(root.id, observed(), expected_revision=root.revision)
    with pytest.raises(WrongNodeKind):
        await collect(filesystem.read(root.id))

    assert consumed == []
    assert await filesystem.get_root() == root
