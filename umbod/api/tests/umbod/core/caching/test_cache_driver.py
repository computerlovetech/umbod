import asyncio
from typing import Literal
from unittest.mock import AsyncMock

import pytest

from tests.umbod.core.caching.support import read_after_signalling, wait_for_signal
from umbod.core.caching import AsyncRequestCache, CacheStorageKey, RequestCache
from umbod.core.key_value import KeyValueDriver, KeyValueHit, KeyValueMiss
from umbod.infrastructure import create_inmemory_key_value_driver


class SuspendedDriver:
    def __init__(
        self, driver: KeyValueDriver[CacheStorageKey[str], object],
        operation: Literal["get", "set"], fail_after_release: bool,
    ) -> None:
        self._driver = driver
        self._operation = operation
        self._fail_after_release = fail_after_release
        self._paused = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.gets = 0
        self.sets = 0

    async def _pause(self, operation: str) -> None:
        if operation != self._operation or self._paused:
            return
        self._paused = True
        self.entered.set()
        await self.release.wait()
        if self._fail_after_release:
            raise RuntimeError("Driver unavailable")

    async def get(self, key: CacheStorageKey[str]) -> KeyValueHit[object] | KeyValueMiss:
        self.gets += 1
        result = await self._driver.get(key)
        await self._pause("get")
        return result

    async def set(self, key: CacheStorageKey[str], value: object) -> None:
        self.sets += 1
        await self._pause("set")
        await self._driver.set(key, value)

    async def delete(self, key: CacheStorageKey[str]) -> None:
        await self._driver.delete(key)

    async def clear(self) -> None:
        await self._driver.clear()


class CommittedWriteDriver(SuspendedDriver):
    async def set(self, key: CacheStorageKey[str], value: object) -> None:
        self.sets += 1
        await self._driver.set(key, value)
        await self._pause("set")


@pytest.fixture
def storage() -> KeyValueDriver[CacheStorageKey[str], object]:
    return create_inmemory_key_value_driver()


@pytest.mark.asyncio
async def test_successful_values_are_read_from_injected_driver() -> None:
    driver = AsyncMock(spec=KeyValueDriver)
    driver.get.side_effect = [KeyValueMiss(), KeyValueHit("stored")]
    cache: AsyncRequestCache[str, object] = RequestCache(driver)
    loader = AsyncMock(return_value="stored")
    assert await cache.get_or_load("key", loader) == "stored"
    assert await cache.get_or_load("key", loader) == "stored"
    assert driver.get.await_count == 2
    driver.set.assert_awaited_once()
    loader.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidate_all", [False, True])
async def test_caches_sharing_driver_keep_namespaces_and_invalidation_isolated(
    storage: KeyValueDriver[CacheStorageKey[str], object], invalidate_all: bool,
) -> None:
    first: AsyncRequestCache[str, object] = RequestCache(storage)
    second: AsyncRequestCache[str, object] = RequestCache(storage)
    assert await first.get_or_load("key", AsyncMock(return_value="first")) == "first"
    assert await second.get_or_load("key", AsyncMock(return_value="second")) == "second"
    if invalidate_all:
        first.clear()
    else:
        first.invalidate("key")
    assert await first.get_or_load("key", AsyncMock(return_value="fresh")) == "fresh"
    unused = AsyncMock()
    assert await second.get_or_load("key", unused) == "second"
    unused.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_driver_lookup_is_shared_before_loader_starts(
    storage: KeyValueDriver[CacheStorageKey[str], object],
) -> None:
    driver = SuspendedDriver(storage, "get", False)
    cache: AsyncRequestCache[str, object] = RequestCache(driver)
    loader = AsyncMock(return_value="loaded")
    leader = asyncio.create_task(cache.get_or_load("key", loader))
    await wait_for_signal(driver.entered)
    entered = asyncio.Event()
    waiter = asyncio.create_task(read_after_signalling(cache, "key", loader, entered))
    await wait_for_signal(entered)
    loader.assert_not_awaited()
    assert driver.gets == 1
    driver.release.set()
    assert await asyncio.gather(leader, waiter) == ["loaded", "loaded"]
    assert driver.gets == 1
    assert driver.sets == 1
    loader.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "set"])
@pytest.mark.parametrize("invalidate_all", [False, True])
@pytest.mark.parametrize("fail_after_release", [False, True])
async def test_invalidation_during_driver_io_preserves_replacement(
    storage: KeyValueDriver[CacheStorageKey[str], object], operation: Literal["get", "set"],
    invalidate_all: bool, fail_after_release: bool,
) -> None:
    driver = SuspendedDriver(storage, operation, fail_after_release)
    cache: AsyncRequestCache[str, object] = RequestCache(driver)
    leader = asyncio.create_task(cache.get_or_load("key", AsyncMock(return_value="old")))
    await wait_for_signal(driver.entered)
    entered = asyncio.Event()
    waiter = asyncio.create_task(read_after_signalling(cache, "key", AsyncMock(), entered))
    await wait_for_signal(entered)
    if invalidate_all:
        cache.clear()
    else:
        cache.invalidate("key")
    assert await cache.get_or_load("key", AsyncMock(return_value="fresh")) == "fresh"
    driver.release.set()
    results = await asyncio.gather(leader, waiter, return_exceptions=True)
    if fail_after_release:
        assert all(isinstance(result, RuntimeError) for result in results)
    else:
        assert results == ["old", "old"]
    unused = AsyncMock()
    assert await cache.get_or_load("key", unused) == "fresh"
    unused.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "set"])
async def test_driver_failure_propagates_to_waiters_and_next_call_retries(
    storage: KeyValueDriver[CacheStorageKey[str], object], operation: Literal["get", "set"],
) -> None:
    driver = SuspendedDriver(storage, operation, True)
    cache: AsyncRequestCache[str, object] = RequestCache(driver)
    leader = asyncio.create_task(cache.get_or_load("key", AsyncMock(return_value="old")))
    await wait_for_signal(driver.entered)
    entered = asyncio.Event()
    waiter = asyncio.create_task(read_after_signalling(cache, "key", AsyncMock(), entered))
    await wait_for_signal(entered)
    driver.release.set()
    results = await asyncio.gather(leader, waiter, return_exceptions=True)
    assert all(isinstance(result, RuntimeError) for result in results)
    assert await cache.get_or_load("key", AsyncMock(return_value="retry")) == "retry"


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_initiator", [False, True])
async def test_failed_or_cancelled_committed_write_cannot_be_reused(
    storage: KeyValueDriver[CacheStorageKey[str], object], cancel_initiator: bool,
) -> None:
    driver = CommittedWriteDriver(storage, "set", True)
    cache: AsyncRequestCache[str, object] = RequestCache(driver)
    leader = asyncio.create_task(cache.get_or_load("key", AsyncMock(return_value="unacknowledged")))
    await wait_for_signal(driver.entered)
    entered = asyncio.Event()
    waiter = asyncio.create_task(read_after_signalling(cache, "key", AsyncMock(), entered))
    await wait_for_signal(entered)
    if cancel_initiator:
        leader.cancel()
    else:
        driver.release.set()
    results = await asyncio.gather(leader, waiter, return_exceptions=True)
    expected = asyncio.CancelledError if cancel_initiator else RuntimeError
    assert all(isinstance(result, expected) for result in results)
    fresh = AsyncMock(return_value="fresh")
    assert await cache.get_or_load("key", fresh) == "fresh"
    fresh.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "set"])
async def test_cancellation_during_driver_io_cancels_waiters_and_allows_retry(
    storage: KeyValueDriver[CacheStorageKey[str], object], operation: Literal["get", "set"],
) -> None:
    driver = SuspendedDriver(storage, operation, False)
    cache: AsyncRequestCache[str, object] = RequestCache(driver)
    leader = asyncio.create_task(cache.get_or_load("key", AsyncMock(return_value="old")))
    await wait_for_signal(driver.entered)
    entered = asyncio.Event()
    waiter = asyncio.create_task(read_after_signalling(cache, "key", AsyncMock(), entered))
    await wait_for_signal(entered)
    leader.cancel()
    results = await asyncio.gather(leader, waiter, return_exceptions=True)
    assert all(isinstance(result, asyncio.CancelledError) for result in results)
    assert await cache.get_or_load("key", AsyncMock(return_value="retry")) == "retry"
