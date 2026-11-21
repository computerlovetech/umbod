from collections.abc import AsyncIterator

import anyio
import httpcore

from umbod.core.connectors.downstream_mcp.endpoint_access import (
    AnonymousAccessRejected,
    AnonymousInitializationResult,
    AnonymousInitializationSucceeded,
    CheckMcpEndpointAccess,
    EndpointAccessInconclusive,
)
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.validation import (
    validated_url,
)

from .protocol import INITIALIZE_REQUEST, validate_initialization

_HEADERS = [
    (b"accept", b"application/json, text/event-stream"),
    (b"accept-encoding", b"identity"),
    (b"content-type", b"application/json"),
    (b"connection", b"close"),
]


class ResponseTooLarge(ValueError):
    pass


class PublicMcpInitialization:
    def __init__(
        self,
        pool: httpcore.AsyncConnectionPool,
        *,
        timeout_seconds: float,
        maximum_response_bytes: int,
    ) -> None:
        self._pool = pool
        self._timeout_seconds = timeout_seconds
        self._maximum_response_bytes = maximum_response_bytes

    async def initialize(
        self, command: CheckMcpEndpointAccess
    ) -> AnonymousInitializationResult:
        try:
            validated_url(command.endpoint_url)
            with anyio.fail_after(self._timeout_seconds):
                async with self._pool.stream(
                    "POST",
                    command.endpoint_url,
                    headers=_HEADERS,
                    content=INITIALIZE_REQUEST,
                ) as response:
                    return await self._read_response(response)
        except TimeoutError, httpcore.TimeoutException:
            return EndpointAccessInconclusive(reason="timeout")
        except httpcore.ProtocolError:
            return EndpointAccessInconclusive(reason="invalid_mcp_protocol")
        except OSError, httpcore.NetworkError:
            return EndpointAccessInconclusive(reason="unreachable")
        except ValueError, httpcore.UnsupportedProtocol:
            return EndpointAccessInconclusive(reason="unsafe_destination")

    async def _read_response(
        self, response: httpcore.Response
    ) -> AnonymousInitializationResult:
        match response.status:
            case 401:
                return AnonymousAccessRejected(status_code=401)
            case 403:
                return AnonymousAccessRejected(status_code=403)
            case 404 | 410:
                return EndpointAccessInconclusive(reason="endpoint_not_found")
            case status if 300 <= status < 400:
                return EndpointAccessInconclusive(reason="redirected")
            case status if status >= 500:
                return EndpointAccessInconclusive(reason="unreachable")
            case 200:
                return await self._validate_response(response)
            case _:
                return EndpointAccessInconclusive(reason="invalid_mcp_protocol")

    async def _validate_response(
        self, response: httpcore.Response
    ) -> AnonymousInitializationResult:
        headers = {key.lower(): value for key, value in response.headers}
        try:
            if (
                headers.get(b"content-encoding", b"identity").strip().lower()
                != b"identity"
            ):
                return EndpointAccessInconclusive(reason="invalid_mcp_protocol")
            if int(headers.get(b"content-length", b"0")) > self._maximum_response_bytes:
                return EndpointAccessInconclusive(reason="response_too_large")
            media_type = (
                headers.get(b"content-type", b"").partition(b";")[0].strip().lower()
            )
            if await validate_initialization(
                media_type, self._bounded_chunks(response)
            ):
                return AnonymousInitializationSucceeded()
        except ResponseTooLarge:
            return EndpointAccessInconclusive(reason="response_too_large")
        except ValueError, RecursionError:
            return EndpointAccessInconclusive(reason="invalid_mcp_protocol")
        return EndpointAccessInconclusive(reason="invalid_mcp_protocol")

    async def _bounded_chunks(
        self, response: httpcore.Response
    ) -> AsyncIterator[bytes]:
        size = 0
        async for chunk in response.aiter_stream():
            size += len(chunk)
            if size > self._maximum_response_bytes:
                raise ResponseTooLarge
            yield chunk
