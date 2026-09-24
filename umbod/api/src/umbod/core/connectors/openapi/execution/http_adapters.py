import ssl
from contextlib import AbstractAsyncContextManager
from typing import AsyncIterator, Protocol

import httpx
from pydantic import ConfigDict, PositiveFloat, PositiveInt

from umbod.proxies import Model

from umbod.core.connectors.openapi.execution.service import (
    AuthenticatedOutboundRequest,
    ExactHttpsDestinationPolicy,
    OpenApiExecutionResponse,
    OutboundRequest,
    TrustedBearerAuthorization,
)


class AsyncHttpStreamResponse(Protocol):
    status_code: int
    headers: httpx.Headers

    def aiter_bytes(self) -> AsyncIterator[bytes]: ...


class AsyncStreamingHttpClient(Protocol):
    def stream(
        self, method: str, url: str, **kwargs: object
    ) -> AbstractAsyncContextManager[AsyncHttpStreamResponse]: ...


class OutboundTransportError(Exception):
    code: str = "outbound_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


class OutboundPolicyError(OutboundTransportError):
    code = "destination_denied"


class OutboundRedirectError(OutboundTransportError):
    code = "redirect_denied"


class OutboundTimeoutError(OutboundTransportError):
    code = "outbound_timeout"


class OutboundNetworkError(OutboundTransportError):
    code = "outbound_unavailable"


class OutboundTlsError(OutboundTransportError):
    code = "outbound_tls_failed"


class HttpxOutboundOperationAdapter:
    _safe_response_headers = frozenset(
        {"cache-control", "content-language", "etag", "expires", "last-modified", "retry-after"}
    )

    _forbidden_request_headers = frozenset(
        {
            "authorization",
            "cookie",
            "proxy-authorization",
            "host",
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
            "forwarded",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-forwarded-proto",
        }
    )

    def __init__(self, client: AsyncStreamingHttpClient) -> None:
        self._client = client
        self._policy = ExactHttpsDestinationPolicy()

    async def send(
        self, request: AuthenticatedOutboundRequest | OutboundRequest
    ) -> OpenApiExecutionResponse:
        try:
            destination = self._policy.validate(request.url, request.approved_hosts)
        except ValueError:
            raise OutboundPolicyError() from None
        safe_request_headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() not in self._forbidden_request_headers
        }
        if isinstance(request, AuthenticatedOutboundRequest) and isinstance(
            request.authorization, TrustedBearerAuthorization
        ):
            safe_request_headers["Authorization"] = (
                f"Bearer {request.authorization.token.get_secret_value()}"
            )
        arguments: dict[str, object] = {
            "headers": safe_request_headers,
            "timeout": request.timeout_seconds,
            "follow_redirects": False,
        }
        if request.has_json_body:
            arguments["json"] = request.json_body
        try:
            async with self._client.stream(request.method, destination, **arguments) as response:
                if 300 <= response.status_code < 400:
                    raise OutboundRedirectError()
                body = bytearray()
                truncated = False
                async for chunk in response.aiter_bytes():
                    remaining = request.maximum_response_bytes - len(body)
                    if len(chunk) > remaining:
                        body.extend(chunk[:remaining])
                        truncated = True
                        break
                    body.extend(chunk)
                content_type = (
                    response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                )
                safe_headers = {
                    name.lower(): value
                    for name, value in response.headers.items()
                    if name.lower() in self._safe_response_headers
                }
                return OpenApiExecutionResponse(
                    status=response.status_code,
                    content_type=content_type,
                    headers=safe_headers,
                    body=bytes(body),
                    truncated=truncated,
                )
        except OutboundTransportError:
            raise
        except httpx.TimeoutException:
            raise OutboundTimeoutError() from None
        except httpx.ConnectError as error:
            if self._has_tls_cause(error):
                raise OutboundTlsError() from None
            raise OutboundNetworkError() from None
        except httpx.HTTPError:
            raise OutboundNetworkError() from None

    def _has_tls_cause(self, error: BaseException) -> bool:
        current: BaseException | None = error
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            if isinstance(current, (ssl.SSLError, ssl.CertificateError)):
                return True
            visited.add(id(current))
            current = current.__cause__ if current.__cause__ is not None else current.__context__
        return False


class OutboundHttpClientFactory:
    def __init__(
        self,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        write_timeout_seconds: float,
        pool_timeout_seconds: float,
    ) -> None:
        self._timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=write_timeout_seconds,
            pool=pool_timeout_seconds,
        )

    def create(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=self._timeout)


class SpecificationFetchRequest(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    approved_hosts: tuple[str, ...]
    timeout_seconds: PositiveFloat = 10.0
    maximum_response_bytes: PositiveInt = 2_000_000


class SpecificationFetcher(Protocol):
    async def fetch(self, request: SpecificationFetchRequest) -> bytes: ...


class HttpxSpecificationFetcher:
    def __init__(
        self, client: AsyncStreamingHttpClient, policy: ExactHttpsDestinationPolicy
    ) -> None:
        self._client = client
        self._policy = policy

    async def fetch(self, request: SpecificationFetchRequest) -> bytes:
        url = self._policy.validate(request.url, request.approved_hosts)
        async with self._client.stream(
            "GET", url, timeout=request.timeout_seconds, follow_redirects=False
        ) as response:
            if response.status_code < 200 or response.status_code >= 300:
                raise ValueError("Specification fetch failed")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > request.maximum_response_bytes:
                    raise ValueError("Specification exceeds response byte limit")
                body.extend(chunk)
            return bytes(body)
