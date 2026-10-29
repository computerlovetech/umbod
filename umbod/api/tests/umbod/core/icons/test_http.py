from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import httpcore
import pytest

from umbod.core.icons.adapters.http import PublicFaviconHttpClient
from umbod.core.icons.http_models import FaviconHttpPolicy, FaviconHttpRequest, FaviconHttpResponse, FaviconHttpUnavailable
from umbod.core.icons.http_ports import FaviconHttpClient


URL = "https://example.com/favicon.ico"


class ChunkStream:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.consumed = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.consumed += 1
            yield chunk

    async def aclose(self) -> None:
        pass


class FailingStream:
    def __aiter__(self) -> AsyncIterator[bytes]:
        raise httpcore.ReadError("disconnected")

    async def aclose(self) -> None:
        pass


class FakePool:
    def __init__(self, responses: list[httpcore.Response | Exception]) -> None:
        self.responses = iter(responses)
        self.requests: list[tuple[str, str, dict[str, str]]] = []

    @asynccontextmanager
    async def stream(self, method: str, url: str, headers: dict[str, str], extensions: dict[str, object]) -> AsyncIterator[httpcore.Response]:
        self.requests.append((method, url, headers))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        try:
            yield response
        finally:
            await response.aclose()


def client(pool: object, limit: int, redirects: int) -> FaviconHttpClient:
    return PublicFaviconHttpClient(
        cast(httpcore.AsyncConnectionPool, pool),
        FaviconHttpPolicy(max_body_bytes=limit, max_redirects=redirects, timeout_seconds=1),
    )


@pytest.mark.asyncio
async def test_http_response_normalizes_media_type_and_accepts_exact_byte_limit() -> None:
    pool = FakePool([httpcore.Response(200, headers={b"content-type": b"IMAGE/PNG; charset=binary"}, content=b"1234")])
    result = await client(pool, 4, 0).fetch(FaviconHttpRequest(url=URL))
    assert isinstance(result, FaviconHttpResponse)
    assert result.body == b"1234"
    assert result.content_type == "image/png"
    assert str(result.url) == URL


@pytest.mark.asyncio
async def test_streaming_limit_stops_consumption_before_remaining_chunks() -> None:
    stream = ChunkStream([b"123", b"45", b"never read"])
    pool = FakePool([httpcore.Response(200, content=stream)])
    result = await client(pool, 4, 0).fetch(FaviconHttpRequest(url=URL))
    assert isinstance(result, FaviconHttpUnavailable)
    assert stream.consumed == 2


@pytest.mark.asyncio
async def test_oversized_content_length_rejects_without_consuming_stream() -> None:
    stream = ChunkStream([b"12345"])
    pool = FakePool([httpcore.Response(200, headers={b"content-length": b"5"}, content=stream)])
    assert isinstance(await client(pool, 4, 0).fetch(FaviconHttpRequest(url=URL)), FaviconHttpUnavailable)
    assert stream.consumed == 0


@pytest.mark.parametrize("encoding", [b"gzip", b"br", b"deflate", b"identity, gzip"])
@pytest.mark.asyncio
async def test_unsupported_content_encoding_is_unavailable(encoding: bytes) -> None:
    stream = ChunkStream([b"compressed"])
    pool = FakePool([httpcore.Response(200, headers={b"content-encoding": encoding}, content=stream)])
    assert isinstance(await client(pool, 64, 0).fetch(FaviconHttpRequest(url=URL)), FaviconHttpUnavailable)
    assert stream.consumed == 0


@pytest.mark.parametrize("status", [204, 400, 401, 404, 500])
@pytest.mark.asyncio
async def test_non_successful_response_is_unavailable(status: int) -> None:
    pool = FakePool([httpcore.Response(status, content=b"error")])
    assert isinstance(await client(pool, 64, 0).fetch(FaviconHttpRequest(url=URL)), FaviconHttpUnavailable)


@pytest.mark.asyncio
async def test_redirect_cap_stops_without_requesting_next_destination() -> None:
    pool = FakePool([
        httpcore.Response(302, headers={b"location": b"/second"}),
        httpcore.Response(302, headers={b"location": b"/third"}),
    ])
    assert isinstance(await client(pool, 64, 1).fetch(FaviconHttpRequest(url=URL)), FaviconHttpUnavailable)
    assert [request[1] for request in pool.requests] == [URL, "https://example.com/second"]


@pytest.mark.asyncio
async def test_redirect_resolves_relative_url_and_does_not_forward_cookies_or_authorization() -> None:
    pool = FakePool([
        httpcore.Response(302, headers={b"location": b"/next#fragment", b"set-cookie": b"secret=value"}),
        httpcore.Response(200, content=b"icon"),
    ])
    result = await client(pool, 64, 1).fetch(FaviconHttpRequest(url=URL))
    assert isinstance(result, FaviconHttpResponse)
    assert str(result.url) == "https://example.com/next"
    assert [request[2] for request in pool.requests] == [
        {"Accept": "image/*, text/html;q=0.8", "Accept-Encoding": "identity"},
        {"Accept": "image/*, text/html;q=0.8", "Accept-Encoding": "identity"},
    ]


@pytest.mark.parametrize("location", [b"file:///etc/passwd", b"https://user:secret@example.com/icon", b"https://example.com:0/icon", b"https://example.com/%00icon"])
@pytest.mark.asyncio
async def test_redirect_destination_is_revalidated_before_request(location: bytes) -> None:
    pool = FakePool([httpcore.Response(302, headers={b"location": location})])
    assert isinstance(await client(pool, 64, 1).fetch(FaviconHttpRequest(url=URL)), FaviconHttpUnavailable)
    assert len(pool.requests) == 1


@pytest.mark.asyncio
async def test_redirect_without_location_is_unavailable() -> None:
    pool = FakePool([httpcore.Response(302)])
    assert isinstance(await client(pool, 64, 1).fetch(FaviconHttpRequest(url=URL)), FaviconHttpUnavailable)


@pytest.mark.parametrize("error", [httpcore.ConnectError("offline"), httpcore.ReadTimeout("slow"), httpcore.RemoteProtocolError("bad"), OSError("dns"), ValueError("private address"), TimeoutError("deadline")])
@pytest.mark.asyncio
async def test_transport_errors_are_unavailable(error: Exception) -> None:
    pool = FakePool([error])
    assert isinstance(await client(pool, 64, 0).fetch(FaviconHttpRequest(url=URL)), FaviconHttpUnavailable)


@pytest.mark.asyncio
async def test_streaming_failure_is_unavailable() -> None:
    stream = FailingStream()
    pool = FakePool([httpcore.Response(200, content=stream)])
    assert isinstance(await client(pool, 64, 0).fetch(FaviconHttpRequest(url=URL)), FaviconHttpUnavailable)
