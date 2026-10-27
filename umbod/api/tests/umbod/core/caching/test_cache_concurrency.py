import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.umbod.core.caching.support import ControlledLoader, read_after_signalling, wait_for_signal
from umbod.core.caching import AsyncRequestCache


@pytest.mark.asyncio
async def test_concurrent_equal_keys_share_one_successful_load(
    cache: AsyncRequestCache[str, object],
) -> None:
    loader = ControlledLoader(object())
    leader = asyncio.create_task(cache.get_or_load("key", loader))
    await wait_for_signal(loader.started)
    entered = [asyncio.Event() for _ in range(3)]
    unused = AsyncMock()
    waiters = [
        asyncio.create_task(read_after_signalling(cache, "key", unused, signal))
        for signal in entered
    ]
    for signal in entered:
        await wait_for_signal(signal)
    loader.release.set()
    results = await asyncio.gather(leader, *waiters)
    assert all(value is loader.value for value in results)
    assert loader.calls == 1
    unused.assert_not_awaited()


@pytest.mark.asyncio
async def test_unrelated_key_can_finish_while_another_load_is_blocked(
    cache: AsyncRequestCache[str, object],
) -> None:
    loader = ControlledLoader("blocked")
    leader = asyncio.create_task(cache.get_or_load("blocked", loader))
    await wait_for_signal(loader.started)
    assert await cache.get_or_load("independent", AsyncMock(return_value="ready")) == "ready"
    assert not leader.done()
    loader.release.set()
    assert await leader == "blocked"


@pytest.mark.asyncio
async def test_concurrent_equal_keys_share_failure_then_allow_retry(
    cache: AsyncRequestCache[str, object],
) -> None:
    gate = ControlledLoader("unused")
    failure = ValueError("unavailable")

    async def fail() -> object:
        await gate()
        raise failure

    leader = asyncio.create_task(cache.get_or_load("key", fail))
    await wait_for_signal(gate.started)
    entered = asyncio.Event()
    unused = AsyncMock()
    waiter = asyncio.create_task(read_after_signalling(cache, "key", unused, entered))
    await wait_for_signal(entered)
    gate.release.set()
    results = await asyncio.gather(leader, waiter, return_exceptions=True)
    assert all(result is failure for result in results)
    unused.assert_not_awaited()
    assert await cache.get_or_load("key", AsyncMock(return_value="recovered")) == "recovered"


@pytest.mark.asyncio
async def test_cancelling_waiter_does_not_cancel_load_or_other_callers(
    cache: AsyncRequestCache[str, object],
) -> None:
    loader = ControlledLoader("loaded")
    leader = asyncio.create_task(cache.get_or_load("key", loader))
    await wait_for_signal(loader.started)
    entered = asyncio.Event()
    waiter = asyncio.create_task(read_after_signalling(cache, "key", loader, entered))
    await wait_for_signal(entered)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert not leader.done()
    loader.release.set()
    assert await leader == "loaded"
    assert await cache.get_or_load("key", AsyncMock()) == "loaded"
    assert loader.calls == 1


@pytest.mark.asyncio
async def test_cancelling_initiator_cancels_waiters_and_allows_retry(
    cache: AsyncRequestCache[str, object],
) -> None:
    loader = ControlledLoader("unused")
    leader = asyncio.create_task(cache.get_or_load("key", loader))
    await wait_for_signal(loader.started)
    entered = asyncio.Event()
    waiter = asyncio.create_task(read_after_signalling(cache, "key", loader, entered))
    await wait_for_signal(entered)
    leader.cancel()
    results = await asyncio.gather(leader, waiter, return_exceptions=True)
    assert all(isinstance(result, asyncio.CancelledError) for result in results)
    assert await cache.get_or_load("key", AsyncMock(return_value="retry")) == "retry"
