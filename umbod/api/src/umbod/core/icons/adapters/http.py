import asyncio
from urllib.parse import urldefrag, urljoin

import httpcore

from ..http_models import (
    FaviconHttpPolicy,
    FaviconHttpRequest,
    FaviconHttpResponse,
    FaviconHttpResult,
    FaviconHttpUnavailable,
)
from .network import validate_favicon_url


class PublicFaviconHttpClient:
    def __init__(self, pool: httpcore.AsyncConnectionPool, policy: FaviconHttpPolicy) -> None:
        self._pool = pool
        self._policy = policy

    async def fetch(self, request: FaviconHttpRequest) -> FaviconHttpResult:
        try:
            async with asyncio.timeout(self._policy.timeout_seconds):
                return await self._fetch_redirects(str(request.url))
        except (httpcore.NetworkError, httpcore.ProtocolError, httpcore.TimeoutException, ValueError, OSError):
            return FaviconHttpUnavailable()

    async def _fetch_redirects(self, url: str) -> FaviconHttpResult:
        timeout = self._policy.timeout_seconds
        for redirect_count in range(self._policy.max_redirects + 1):
            validate_favicon_url(url)
            async with self._pool.stream(
                "GET",
                url,
                headers={"Accept": "image/*, text/html;q=0.8", "Accept-Encoding": "identity"},
                extensions={"timeout": {"connect": timeout, "read": timeout, "write": timeout, "pool": timeout}},
            ) as response:
                headers = {key.lower(): value for key, value in response.headers}
                if 300 <= response.status < 400:
                    if redirect_count == self._policy.max_redirects or b"location" not in headers:
                        return FaviconHttpUnavailable()
                    url = urldefrag(urljoin(url, headers[b"location"].decode("ascii")))[0]
                    continue
                if response.status != 200:
                    return FaviconHttpUnavailable()
                if headers.get(b"content-encoding", b"identity").lower() != b"identity":
                    return FaviconHttpUnavailable()
                if int(headers.get(b"content-length", b"0")) > self._policy.max_body_bytes:
                    return FaviconHttpUnavailable()
                body = bytearray()
                async for chunk in response.aiter_stream():
                    if len(body) + len(chunk) > self._policy.max_body_bytes:
                        return FaviconHttpUnavailable()
                    body.extend(chunk)
                return FaviconHttpResponse(
                    url=url,
                    status=response.status,
                    content_type=headers.get(b"content-type", b"").decode("ascii").split(";", 1)[0].strip().lower(),
                    body=bytes(body),
                )
        return FaviconHttpUnavailable()
