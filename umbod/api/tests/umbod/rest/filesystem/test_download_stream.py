from uuid import uuid4

import pytest
from starlette.requests import ClientDisconnect
from starlette.types import Message, Scope

from umbod.core.filesystem import ByteStream, NodeKind, NodeMetadata, StorageFailure
from umbod.core.filesystem.browsing import summary
from umbod.core.filesystem.content import ContentDownload
from umbod.core.filesystem.namespace import new_node
from umbod.rest.filesystem.downloads import download_response


def download(stream: ByteStream) -> ContentDownload:
    node = new_node(
        uuid4(), "download.bin", NodeKind.FILE,
        NodeMetadata(content_type="application/octet-stream", attributes={}),
    )
    return ContentDownload(node=summary(node), data=stream, size=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_message", ["http.response.start", "http.response.body"])
async def test_failed_asgi_send_closes_prefetched_content_stream(failed_message: str) -> None:
    closed: list[bool] = []

    async def chunks() -> ByteStream:
        try:
            yield b"a"
            yield b"b"
        finally:
            closed.append(True)

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == failed_message:
            raise OSError("Disconnected")

    response = await download_response(download(chunks()))
    scope: Scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    with pytest.raises(ClientDisconnect):
        await response(scope, receive, send)
    assert closed == [True]


@pytest.mark.asyncio
async def test_first_read_storage_failure_returns_safe_error_and_closes_stream() -> None:
    from fastapi import HTTPException

    closed: list[bool] = []

    async def chunks() -> ByteStream:
        try:
            raise StorageFailure("Private storage details")
            yield b""
        finally:
            closed.append(True)

    with pytest.raises(HTTPException) as raised:
        await download_response(download(chunks()))
    assert raised.value.status_code == 500
    assert raised.value.detail == {
        "code": "filesystem_storage_failure", "message": "Filesystem operation failed.",
    }
    assert closed == [True]
