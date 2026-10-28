import re
from collections.abc import AsyncIterator, Mapping

from starlette.types import Receive, Scope, Send
from urllib.parse import quote

from fastapi.responses import StreamingResponse

from umbod.core.filesystem import ByteStream
from umbod.core.filesystem.content import ContentDownload

from .errors import filesystem_errors

DOWNLOAD_RESPONSES = {
    200: {
        "description": "File contents as an attachment. Clients must also support temporary redirects.",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    },
    307: {"description": "Temporary redirect to a short-lived storage URL; follow without forwarding API credentials."},
    403: {"description": "Filesystem access denied."},
    409: {"description": "Node is not a file."},
}


async def close_stream(stream: ByteStream) -> None:
    close = getattr(stream, "aclose", None)
    if close is not None:
        await close()


async def download_chunks(first: bytes, stream: ByteStream) -> AsyncIterator[bytes]:
    yield first
    async for chunk in stream:
        yield chunk


class AttachmentResponse(StreamingResponse):
    def __init__(
        self, download: ContentDownload, first: bytes, media_type: str, headers: Mapping[str, str],
    ) -> None:
        super().__init__(download_chunks(first, download.data), media_type=media_type, headers=headers)
        self._source = download.data

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await close_stream(self._source)


async def download_response(download: ContentDownload) -> StreamingResponse:
    try:
        with filesystem_errors():
            first = await anext(download.data, b"")
    except BaseException:
        await close_stream(download.data)
        raise
    content_type = download.node.metadata.content_type
    media_type = (
        content_type if isinstance(content_type, str)
        and re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", content_type)
        else "application/octet-stream"
    )
    return AttachmentResponse(
        download, first, media_type,
        headers={
            "Content-Disposition": "attachment; filename=\"download\"; filename*=UTF-8''" + quote(download.node.name, safe=""),
            "Content-Length": str(download.size),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
