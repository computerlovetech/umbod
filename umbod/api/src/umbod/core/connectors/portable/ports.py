from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from pydantic import JsonValue


type HttpDispatch = Callable[[object], Awaitable[dict[str, object]]]


class PortableExecutionError(RuntimeError):
    pass


class PortableSession(Protocol):
    async def manifest(self) -> object: ...

    async def run(self, handler_id: str, arguments: dict[str, JsonValue], *, use_http: bool) -> object: ...


class PortableSandbox(Protocol):
    def open(self, source: str, dispatch: HttpDispatch) -> AbstractAsyncContextManager[PortableSession]: ...
