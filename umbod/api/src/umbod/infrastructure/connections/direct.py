from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Generic, TypeVar

from .lifecycle import complete_cleanup

T = TypeVar("T")


class UnpooledConnectionProvider(Generic[T]):
    def __init__(
        self,
        connection_factory: Callable[[], Awaitable[T]],
        connection_closer: Callable[[T], Awaitable[None]],
    ) -> None:
        self._connection_factory = connection_factory
        self._connection_closer = connection_closer

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[T]:
        connection = await self._connection_factory()
        try:
            yield connection
        finally:
            await complete_cleanup(self._connection_closer(connection))
