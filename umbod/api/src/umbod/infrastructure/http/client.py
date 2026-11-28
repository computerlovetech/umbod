from collections.abc import Mapping
from typing import Annotated, Self
from urllib.parse import urljoin, urlsplit

import anyio
import httpx
from pydantic import (
    ConfigDict,
    Field,
    FiniteFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)


from umbod.proxies import Model
from umbod.core.network.http import (
    AsyncHttpClient,
    ClientHttpTimeout,
    HttpRedirectPolicy,
    HttpRequest,
    HttpTransportError,
    NoHttpBody,
    OriginBoundHttpClient,
)

from .httpx_client import HttpxClientProxy


class HttpRequestError(RuntimeError):
    pass


class OutboundHttpClientOptions(Model):
    model_config = ConfigDict(frozen=True, extra="forbid")

    use_environment_settings: bool
    follow_redirects: bool
    max_connections: PositiveInt
    max_idle_connections: NonNegativeInt
    idle_connection_timeout_seconds: Annotated[FiniteFloat, Field(ge=0)]

    @model_validator(mode="after")
    def validate_pool_limits(self) -> Self:
        if self.max_idle_connections > self.max_connections:
            raise ValueError("Maximum idle connections must not exceed maximum connections")
        return self


_HARDENED_OUTBOUND_HTTP_CLIENT_OPTIONS = OutboundHttpClientOptions(
    use_environment_settings=False,
    follow_redirects=False,
    max_connections=100,
    max_idle_connections=20,
    idle_connection_timeout_seconds=5.0,
)


class OutboundHttpClientFactory:
    def __init__(
        self,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        write_timeout_seconds: float,
        pool_timeout_seconds: float,
        *,
        options: OutboundHttpClientOptions,
    ) -> None:
        self._options = options
        self._timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=write_timeout_seconds,
            pool=pool_timeout_seconds,
        )

    @classmethod
    def hardened(
        cls,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        write_timeout_seconds: float,
        pool_timeout_seconds: float,
    ) -> Self:
        return cls(
            connect_timeout_seconds,
            read_timeout_seconds,
            write_timeout_seconds,
            pool_timeout_seconds,
            options=_HARDENED_OUTBOUND_HTTP_CLIENT_OPTIONS,
        )

    def create(self) -> AsyncHttpClient:
        return self._create("")

    def create_for_origin(self, base_url: str) -> OriginBoundHttpClient:
        return self._create(base_url)

    def _create(self, base_url: str) -> HttpxClientProxy:
        client = httpx.AsyncClient(
            base_url=base_url,
            trust_env=self._options.use_environment_settings,
            follow_redirects=self._options.follow_redirects,
            timeout=self._timeout,
            limits=httpx.Limits(
                max_connections=self._options.max_connections,
                max_keepalive_connections=self._options.max_idle_connections,
                keepalive_expiry=self._options.idle_connection_timeout_seconds,
            ),
        )
        return HttpxClientProxy(client)


class JsonHttpLimits(Model):
    model_config = ConfigDict(frozen=True)

    timeout_seconds: PositiveFloat = 10.0
    maximum_response_bytes: PositiveInt = 4_000_000


class AsyncJsonHttpClient:
    def __init__(self, client: OriginBoundHttpClient, *, limits: JsonHttpLimits) -> None:
        base_url = urlsplit(client.base_url)
        if base_url.scheme not in {"http", "https"} or not base_url.hostname:
            raise ValueError("An HTTP base URL is required")
        self._client = client
        self._base_url = client.base_url
        self._limits = limits

    async def get_json(self, path: str, *, params: Mapping[str, str | int]) -> bytes:
        if (
            not path.startswith("/")
            or path.startswith("//")
            or any(character in path for character in "\\?#")
            or any(character.isspace() or ord(character) < 32 for character in path)
        ):
            raise ValueError("An origin-relative HTTP path is required")
        request = HttpRequest(
            method="GET",
            url=urljoin(self._base_url, path),
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            query=params,
            body=NoHttpBody(),
            timeout=ClientHttpTimeout.DEFAULT,
            redirects=HttpRedirectPolicy.DENY,
        )
        try:
            with anyio.fail_after(self._limits.timeout_seconds):
                async with self._client.stream(request) as response:
                    if not 200 <= response.status_code < 300:
                        raise HttpRequestError("HTTP request failed")
                    headers = {name.lower(): value for name, value in response.headers.items()}
                    if headers.get("content-encoding", "identity").lower() != "identity":
                        raise HttpRequestError(
                            "HTTP response uses unsupported content encoding"
                        )
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > self._limits.maximum_response_bytes:
                            raise HttpRequestError(
                                "HTTP response exceeds the size limit"
                            )
                        body.extend(chunk)
                    return bytes(body)
        except HttpTransportError, TimeoutError:
            raise HttpRequestError("HTTP request failed") from None
