import pytest

from tests.support.virtual_filesystem import (
    FilesystemAcceptanceContext,
    MetadataValue,
    NoContentReference,
    StoredContentView,
    UntypedMetadataValue,
)


@pytest.mark.asyncio
async def test_written_stream_is_complete_readable_and_revisioned(
    filesystem_context: FilesystemAcceptanceContext,
) -> None:
    filesystem = filesystem_context.filesystem
    root = await filesystem.root()
    file = await filesystem.create_file(
        root.node, "payload.bin", MetadataValue("application/octet-stream", {"source": "sensor"}),
    )
    payload = b"first\x00segment\xff" + bytes(range(256)) + b"last\r\nsegment"

    written = await filesystem.write_file(file.node, payload, file.revision)

    assert written.node == file.node
    assert written.revision > file.revision
    assert written.updated_at >= file.updated_at
    assert written.created_at == file.created_at
    assert await filesystem.node(file.node) == written
    assert await filesystem.read_file(file.node) == payload
    reference = await filesystem_context.observations.content_reference(file.node)
    assert isinstance(reference, StoredContentView)
    assert reference.size == len(payload)
    assert await filesystem_context.observations.stored_bytes(reference.content) == payload


@pytest.mark.asyncio
async def test_contentless_file_reads_as_an_empty_stream(
    filesystem_context: FilesystemAcceptanceContext,
) -> None:
    filesystem = filesystem_context.filesystem
    root = await filesystem.root()
    file = await filesystem.create_file(root.node, "empty.txt", UntypedMetadataValue({}))

    assert await filesystem.read_file(file.node) == b""
    assert isinstance(
        await filesystem_context.observations.content_reference(file.node), NoContentReference,
    )
