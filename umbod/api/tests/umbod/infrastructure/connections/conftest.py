import asyncio
from collections.abc import AsyncIterator

import pytest_asyncio

from umbod.infrastructure.connections import ConnectionPool, ConnectionProvider


class FakeConnectionDriver:
    def __init__(self) -> None:
        self.opened: list[object] = []
        self.closed: list[object] = []
        self.reset_connections: list[object] = []
        self.connect_calls = 0
        self.fail_connect_at = 0
        self.pause_connect_at = 0
        self.fail_reset = False
        self.fail_close = False
        self.connect_started = asyncio.Event()
        self.connect_allowed = asyncio.Event()
        self.connect_allowed.set()
        self.reset_started = asyncio.Event()
        self.reset_allowed = asyncio.Event()
        self.reset_allowed.set()
        self.close_started = asyncio.Event()
        self.close_allowed = asyncio.Event()
        self.close_allowed.set()

    async def connect(self) -> object:
        self.connect_calls += 1
        if self.pause_connect_at in (0, self.connect_calls):
            self.connect_started.set()
            await self.connect_allowed.wait()
        if self.connect_calls == self.fail_connect_at:
            raise RuntimeError("connect failed")
        connection = object()
        self.opened.append(connection)
        return connection

    async def reset(self, connection: object) -> None:
        self.reset_started.set()
        await self.reset_allowed.wait()
        self.reset_connections.append(connection)
        if self.fail_reset:
            raise RuntimeError("reset failed")

    async def close(self, connection: object) -> None:
        self.close_started.set()
        await self.close_allowed.wait()
        self.closed.append(connection)
        if self.fail_close:
            raise RuntimeError("close failed")


@pytest_asyncio.fixture
async def driver() -> AsyncIterator[FakeConnectionDriver]:
    driver = FakeConnectionDriver()
    try:
        yield driver
    finally:
        driver.connect_allowed.set()
        driver.reset_allowed.set()
        driver.close_allowed.set()


@pytest_asyncio.fixture
async def provider(
    driver: FakeConnectionDriver,
) -> AsyncIterator[ConnectionProvider[object]]:
    pool = ConnectionPool(driver, 2)
    await pool.initialize()
    try:
        yield pool
    finally:
        driver.fail_reset = False
        driver.fail_close = False
        driver.connect_allowed.set()
        driver.reset_allowed.set()
        driver.close_allowed.set()
        await asyncio.wait_for(pool.close(), 2)
