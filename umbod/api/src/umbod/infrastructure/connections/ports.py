from contextlib import AbstractAsyncContextManager
from typing import Protocol, TypeVar

T = TypeVar("T")


class ConnectionDriver(Protocol[T]):
    async def connect(self) -> T: ...

    async def reset(self, connection: T) -> None: ...

    async def close(self, connection: T) -> None: ...


class ConnectionProvider(Protocol[T]):
    def get_connection(self) -> AbstractAsyncContextManager[T]: ...

    async def initialize(self) -> None: ...

    async def close(self) -> None: ...
