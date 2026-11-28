import ssl
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx

from umbod.core.network.http import (
    AsyncHttpStreamResponse,
    ClientHttpTimeout,
    HttpRedirectPolicy,
    HttpRequest,
    HttpTimeoutError,
    HttpTlsError,
    HttpTransportError,
    JsonHttpBody,
)
from umbod.infrastructure.connections.lifecycle import complete_cleanup


@dataclass(frozen=True)
class _StreamingResponse:
    status_code: int
    headers: Mapping[str, str] = field(repr=False)
    chunks: AsyncIterator[bytes] = field(repr=False)

    def aiter_bytes(self) -> AsyncIterator[bytes]:
        return self.chunks


class HttpxClientProxy:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    @asynccontextmanager
    async def stream(self, request: HttpRequest) -> AsyncIterator[AsyncHttpStreamResponse]:
        try:
            response = await self._send(request)
            try:
                yield _StreamingResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers.items()),
                    chunks=_read_chunks(response),
                )
            finally:
                await complete_cleanup(response.aclose())
        except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError) as error:
            raise _transport_error(error) from error

    async def _send(self, request: HttpRequest) -> httpx.Response:
        outgoing = self._build_request(request)
        redirects = 0
        follow_redirects = (
            request.redirects is HttpRedirectPolicy.CLIENT_DEFAULT and self._client.follow_redirects
        )
        while True:
            response = await self._client.send(outgoing, auth=None, follow_redirects=False, stream=True)
            next_request = response.next_request
            if not follow_redirects or next_request is None:
                return response
            if _origin(next_request.url) != _origin(outgoing.url):
                return response
            await complete_cleanup(response.aclose())
            redirects += 1
            if redirects > self._client.max_redirects:
                raise HttpTransportError("HTTP redirect limit exceeded")
            if "cookie" in outgoing.headers:
                next_request.headers["cookie"] = outgoing.headers["cookie"]
            else:
                next_request.headers.pop("cookie", None)
            outgoing = next_request

    def _build_request(self, request: HttpRequest) -> httpx.Request:
        url = httpx.URL(request.url)
        if not url.is_absolute_url:
            url = self._client.base_url.join(url)
        if request.query:
            url = url.copy_merge_params(request.query)
        headers = httpx.Headers({
            name: self._client.headers[name]
            for name in ("accept", "accept-encoding", "connection", "user-agent")
            if name in self._client.headers
        })
        headers.update(request.headers)
        extensions: dict[str, object] = {}
        if request.timeout is not ClientHttpTimeout.DEFAULT:
            extensions["timeout"] = httpx.Timeout(request.timeout).as_dict()
        if isinstance(request.body, JsonHttpBody):
            if request.body.value is None:
                headers.setdefault("content-type", "application/json")
                return httpx.Request(request.method, url, headers=headers, content=b"null", extensions=extensions)
            return httpx.Request(request.method, url, headers=headers, json=request.body.value, extensions=extensions)
        return httpx.Request(request.method, url, headers=headers, extensions=extensions)

    async def aclose(self) -> None:
        try:
            await complete_cleanup(self._client.aclose())
        except httpx.HTTPError as error:
            raise _transport_error(error) from error


async def _read_chunks(response: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_bytes():
            yield chunk
    except (httpx.HTTPError, httpx.StreamError) as error:
        raise _transport_error(error) from error


def _origin(url: httpx.URL) -> tuple[str, str, int | None]:
    return url.scheme, url.host, url.port


def _transport_error(error: httpx.HTTPError | httpx.InvalidURL | httpx.StreamError) -> HttpTransportError:
    if isinstance(error, httpx.TimeoutException):
        return HttpTimeoutError("HTTP request timed out")
    if isinstance(error, httpx.ConnectError) and _has_tls_cause(error):
        return HttpTlsError("HTTP TLS connection failed")
    return HttpTransportError("HTTP request failed")


def _has_tls_cause(error: BaseException) -> bool:
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        if isinstance(current, (ssl.SSLError, ssl.CertificateError)):
            return True
        visited.add(id(current))
        current = current.__cause__ if current.__cause__ is not None else current.__context__
    return False
