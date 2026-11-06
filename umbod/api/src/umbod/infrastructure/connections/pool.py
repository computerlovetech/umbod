import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import Enum, auto
from typing import Generic, TypeVar

from .lifecycle import complete_cleanup
from .ports import ConnectionDriver

T = TypeVar("T")


class ConnectionPoolUnavailableError(RuntimeError):
    pass


class _State(Enum):
    NEW = auto()
    OPEN = auto()
    CLOSING = auto()
    CLOSED = auto()


class ConnectionPool(Generic[T]):
    def __init__(self, driver: ConnectionDriver[T], size: int) -> None:
        if size < 1:
            raise ValueError("Connection pool size must be at least one")
        self._driver = driver
        self._size = size
        self._state = _State.NEW
        self._available: list[T] = []
        self._borrowed = 0
        self._condition = asyncio.Condition()
        self._lifecycle_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lifecycle_lock:
            if self._state is _State.OPEN:
                return
            if self._state is not _State.NEW:
                raise ConnectionPoolUnavailableError("Connection pool is closed")
            opened: list[T] = []
            try:
                for _ in range(self._size):
                    opened.append(await self._open_connection())
            except BaseException:
                self._state = _State.CLOSED
                try:
                    await complete_cleanup(self._close_connections(opened))
                except BaseException:
                    pass
                raise
            self._available = opened
            self._state = _State.OPEN

    async def _open_connection(self) -> T:
        opening = asyncio.ensure_future(self._driver.connect())
        try:
            return await asyncio.shield(opening)
        except BaseException:

            async def discard_opening() -> None:
                await asyncio.gather(opening, return_exceptions=True)
                if not opening.cancelled() and opening.exception() is None:
                    await self._driver.close(opening.result())

            try:
                await complete_cleanup(discard_opening())
            except BaseException:
                pass
            raise

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[T]:
        async with self._condition:
            await self._condition.wait_for(
                lambda: self._state is not _State.OPEN or self._borrowed < self._size
            )
            if self._state is not _State.OPEN:
                raise ConnectionPoolUnavailableError("Connection pool is not open")
            self._borrowed += 1
            reserved = self._available[-1:]
            if reserved:
                self._available.pop()
        try:
            connection = reserved[0] if reserved else await self._open_connection()
        except BaseException:
            await complete_cleanup(self._return_capacity())
            raise
        try:
            yield connection
        except BaseException:
            try:
                await complete_cleanup(self._release(connection))
            except BaseException:
                pass
            raise
        else:
            await complete_cleanup(self._release(connection))

    async def _return_capacity(self) -> None:
        async with self._condition:
            self._borrowed -= 1
            self._condition.notify_all()

    async def _release(self, connection: T) -> None:
        try:
            try:
                await self._driver.reset(connection)
            except BaseException:
                try:
                    await self._driver.close(connection)
                except BaseException:
                    pass
                raise
            self._available.append(connection)
        finally:
            await self._return_capacity()

    async def close(self) -> None:
        await complete_cleanup(self._close())

    async def _close(self) -> None:
        async with self._lifecycle_lock:
            if self._state is _State.CLOSED:
                return
            async with self._condition:
                self._state = _State.CLOSING
                self._condition.notify_all()
                await self._condition.wait_for(lambda: self._borrowed == 0)
            connections, self._available = self._available, []
            try:
                await self._close_connections(connections)
            finally:
                self._state = _State.CLOSED

    async def _close_connections(self, connections: list[T]) -> None:
        results = await asyncio.gather(
            *(self._driver.close(connection) for connection in connections),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
