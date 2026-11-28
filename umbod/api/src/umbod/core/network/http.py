from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol

from pydantic import JsonValue


class ClientHttpTimeout(Enum):
    DEFAULT = auto()


class HttpRedirectPolicy(Enum):
    CLIENT_DEFAULT = auto()
    DENY = auto()


@dataclass(frozen=True)
class NoHttpBody:
    pass


@dataclass(frozen=True)
class JsonHttpBody:
    value: JsonValue = field(repr=False)


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    query: Mapping[str, str | int] = field(repr=False)
    body: NoHttpBody | JsonHttpBody
    timeout: ClientHttpTimeout | float
    redirects: HttpRedirectPolicy


class AsyncHttpStreamResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def headers(self) -> Mapping[str, str]: ...

    def aiter_bytes(self) -> AsyncIterator[bytes]: ...


class AsyncHttpClient(Protocol):
    def stream(self, request: HttpRequest) -> AbstractAsyncContextManager[AsyncHttpStreamResponse]: ...

    async def aclose(self) -> None: ...


class OriginBoundHttpClient(AsyncHttpClient, Protocol):
    @property
    def base_url(self) -> str: ...


class HttpTransportError(RuntimeError):
    pass


class HttpTimeoutError(HttpTransportError):
    pass


class HttpTlsError(HttpTransportError):
    pass
