import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import TypeVar

import anyio
import pytest

from tests.umbod.infrastructure.connections.conftest import FakeConnectionDriver
from umbod.infrastructure.connections import (
    ConnectionPool,
    ConnectionPoolUnavailableError,
    ConnectionProvider,
)

T = TypeVar("T")
pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def running_task(
    operation: Coroutine[object, object, T], driver: FakeConnectionDriver
) -> AsyncIterator[asyncio.Task[T]]:
    task = asyncio.create_task(operation)
    try:
        yield task
    finally:
        driver.connect_allowed.set()
        driver.reset_allowed.set()
        driver.close_allowed.set()
        if not task.done():
            task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 2)


async def lease(provider: ConnectionProvider[object]) -> object:
    async with provider.get_connection() as connection:
        return connection


@pytest.mark.parametrize("size", [0, -1])
async def test_invalid_capacity_is_rejected(
    driver: FakeConnectionDriver, size: int
) -> None:
    with pytest.raises(ValueError, match="at least one"):
        ConnectionPool(driver, size)


async def test_initialize_eagerly_opens_capacity_once(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    await provider.initialize()
    assert driver.connect_calls == 2
    assert len(driver.opened) == 2


async def test_shutdown_waits_for_initialization_to_finish(
    driver: FakeConnectionDriver,
) -> None:
    pool = ConnectionPool(driver, 2)
    driver.connect_allowed.clear()
    async with running_task(pool.initialize(), driver) as initializing:
        await asyncio.wait_for(driver.connect_started.wait(), 2)
        async with running_task(pool.close(), driver) as closing:
            await asyncio.sleep(0)
            assert not closing.done()
            assert driver.closed == []
            driver.connect_allowed.set()
            await asyncio.wait_for(initializing, 2)
            await asyncio.wait_for(closing, 2)
    assert len(driver.closed) == 2
    assert set(driver.closed) == set(driver.opened)


async def test_initialize_publishes_only_after_all_connections_open(
    driver: FakeConnectionDriver,
) -> None:
    pool = ConnectionPool(driver, 2)
    driver.connect_allowed.clear()
    async with running_task(pool.initialize(), driver) as initializing:
        await asyncio.wait_for(driver.connect_started.wait(), 2)
        with pytest.raises(ConnectionPoolUnavailableError):
            await lease(pool)
        driver.connect_allowed.set()
        await asyncio.wait_for(initializing, 2)
    await pool.close()


async def test_leases_are_exclusive_and_reused(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    async with provider.get_connection() as first:
        async with provider.get_connection() as second:
            assert first is not second
    assert await lease(provider) in (first, second)
    assert driver.connect_calls == 2
    assert len(driver.reset_connections) == 3


async def test_capacity_waiter_receives_released_connection(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    async with provider.get_connection():
        context = provider.get_connection()
        released = await context.__aenter__()
        try:
            async with running_task(lease(provider), driver) as waiting:
                await asyncio.sleep(0)
                assert not waiting.done()
                await context.__aexit__(None, None, None)
                assert await asyncio.wait_for(waiting, 2) is released
        finally:
            if released not in driver.reset_connections:
                await context.__aexit__(None, None, None)


async def test_cancelled_waiter_does_not_lose_capacity(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    async with provider.get_connection():
        async with provider.get_connection():
            async with running_task(lease(provider), driver) as waiting:
                await asyncio.sleep(0)
                waiting.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(waiting, 2)
    async with provider.get_connection() as first:
        async with provider.get_connection() as second:
            assert first is not second


async def test_reset_failure_discards_connection_and_replaces_lazily(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    async with provider.get_connection():
        driver.fail_reset = True
        with pytest.raises(RuntimeError, match="reset failed"):
            await lease(provider)
        driver.fail_reset = False
        assert len(driver.closed) == 1
        discarded = driver.closed[0]
        assert driver.connect_calls == 2
        replacement = await lease(provider)
        assert replacement is not discarded
        assert driver.connect_calls == 3


async def test_body_error_survives_reset_failure(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    driver.fail_reset = True
    with pytest.raises(ValueError, match="body failed"):
        async with provider.get_connection():
            raise ValueError("body failed")
    driver.fail_reset = False
    assert len(driver.closed) == 1


async def test_replacement_failure_returns_reserved_capacity(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    async with provider.get_connection():
        driver.fail_reset = True
        with pytest.raises(RuntimeError, match="reset failed"):
            await lease(provider)
        driver.fail_reset = False
        driver.fail_connect_at = 3
        with pytest.raises(RuntimeError, match="connect failed"):
            await lease(provider)
        driver.fail_connect_at = 0
        assert await asyncio.wait_for(lease(provider), 2) in driver.opened


async def test_repeated_cancellation_waits_for_reset_before_returning_capacity(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    driver.reset_allowed.clear()
    async with running_task(lease(provider), driver) as releasing:
        await asyncio.wait_for(driver.reset_started.wait(), 2)
        for _ in range(3):
            releasing.cancel()
            await asyncio.sleep(0)
            assert not releasing.done()
        driver.reset_allowed.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(releasing, 2)
    async with provider.get_connection() as first:
        async with provider.get_connection() as second:
            assert first is not second


async def test_initialization_failure_closes_every_opened_connection(
    driver: FakeConnectionDriver,
) -> None:
    pool = ConnectionPool(driver, 3)
    driver.fail_connect_at = 3
    driver.fail_close = True
    with pytest.raises(RuntimeError, match="connect failed"):
        await pool.initialize()
    assert len(driver.closed) == 2
    assert set(driver.closed) == set(driver.opened)
    with pytest.raises(ConnectionPoolUnavailableError):
        await lease(pool)
    await pool.close()


@pytest.mark.parametrize("pause_connect_at", [1, 2])
async def test_cancelled_initialization_closes_late_connection(
    driver: FakeConnectionDriver, pause_connect_at: int
) -> None:
    pool = ConnectionPool(driver, 2)
    driver.pause_connect_at = pause_connect_at
    driver.connect_allowed.clear()
    async with running_task(pool.initialize(), driver) as initializing:
        await asyncio.wait_for(driver.connect_started.wait(), 2)
        initializing.cancel()
        await asyncio.sleep(0)
        initializing.cancel()
        driver.connect_allowed.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(initializing, 2)
    assert len(driver.opened) == pause_connect_at
    assert set(driver.closed) == set(driver.opened)
    with pytest.raises(ConnectionPoolUnavailableError):
        await pool.initialize()
    await pool.close()


async def test_cancelled_replacement_closes_late_connection_and_returns_capacity(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    async with provider.get_connection():
        driver.fail_reset = True
        with pytest.raises(RuntimeError, match="reset failed"):
            await lease(provider)
        driver.fail_reset = False
        driver.connect_started.clear()
        driver.connect_allowed.clear()
        async with running_task(lease(provider), driver) as opening:
            await asyncio.wait_for(driver.connect_started.wait(), 2)
            opening.cancel()
            await asyncio.sleep(0)
            opening.cancel()
            driver.connect_allowed.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(opening, 2)
        assert driver.opened[-1] in driver.closed
        replacement = await asyncio.wait_for(lease(provider), 2)
        assert replacement not in driver.closed


async def test_close_drains_active_leases_and_rejects_blocked_waiters(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    acquired = asyncio.Event()
    release = asyncio.Event()

    async def hold_capacity() -> None:
        async with provider.get_connection():
            async with provider.get_connection():
                acquired.set()
                await release.wait()

    async with running_task(hold_capacity(), driver):
        await asyncio.wait_for(acquired.wait(), 2)
        async with running_task(lease(provider), driver) as waiting:
            await asyncio.sleep(0)
            async with running_task(provider.close(), driver) as closing:
                with pytest.raises(ConnectionPoolUnavailableError):
                    await asyncio.wait_for(waiting, 2)
                assert not closing.done()
                assert driver.closed == []
                release.set()
                await asyncio.wait_for(closing, 2)
    assert set(driver.closed) == set(driver.opened)


async def test_repeated_cancellation_during_shutdown_finishes_all_closes(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    driver.close_allowed.clear()
    async with running_task(provider.close(), driver) as closing:
        await asyncio.wait_for(driver.close_started.wait(), 2)
        for _ in range(3):
            closing.cancel()
            await asyncio.sleep(0)
            assert not closing.done()
        driver.close_allowed.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(closing, 2)
    assert set(driver.closed) == set(driver.opened)
    await provider.close()
    assert len(driver.closed) == 2


async def test_close_failure_still_closes_all_connections_and_is_idempotent(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    driver.fail_close = True
    with pytest.raises(RuntimeError, match="close failed"):
        await provider.close()
    assert len(driver.closed) == 2
    await provider.close()
    assert len(driver.closed) == 2


async def test_concurrent_close_is_idempotent(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    await asyncio.wait_for(asyncio.gather(provider.close(), provider.close()), 2)
    assert len(driver.closed) == 2
    with pytest.raises(ConnectionPoolUnavailableError):
        await lease(provider)


async def test_uninitialized_and_closed_pool_reject_leases(
    driver: FakeConnectionDriver,
) -> None:
    pool = ConnectionPool(driver, 1)
    with pytest.raises(ConnectionPoolUnavailableError):
        await lease(pool)
    await pool.close()
    with pytest.raises(ConnectionPoolUnavailableError):
        await lease(pool)
    with pytest.raises(ConnectionPoolUnavailableError):
        await pool.initialize()
    assert driver.connect_calls == 0


async def test_anyio_level_cancellation_completes_release(
    driver: FakeConnectionDriver, provider: ConnectionProvider[object]
) -> None:
    with anyio.CancelScope() as scope:
        async with provider.get_connection():
            scope.cancel()
            await anyio.lowlevel.checkpoint()
    assert len(driver.reset_connections) == 1
    async with provider.get_connection() as first:
        async with provider.get_connection() as second:
            assert first is not second
