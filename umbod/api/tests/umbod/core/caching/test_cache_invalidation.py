import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.umbod.core.caching.support import ControlledLoader, read_after_signalling, wait_for_signal
from umbod.core.caching import AsyncRequestCache


@pytest.mark.asyncio
async def test_invalidate_forgets_only_selected_key(cache: AsyncRequestCache[str, object]) -> None:
    loader = AsyncMock(side_effect=["first", "second", "fresh"])
    assert await cache.get_or_load("first", loader) == "first"
    assert await cache.get_or_load("second", loader) == "second"
    cache.invalidate("first")
    cache.invalidate("missing")
    assert await cache.get_or_load("second", loader) == "second"
    assert await cache.get_or_load("first", loader) == "fresh"
    assert loader.await_count == 3


@pytest.mark.asyncio
async def test_clear_forgets_every_key_and_is_repeatable(cache: AsyncRequestCache[str, object]) -> None:
    loader = AsyncMock(side_effect=["old-first", "old-second", "new-first", "new-second"])
    assert await cache.get_or_load("first", loader) == "old-first"
    assert await cache.get_or_load("second", loader) == "old-second"
    cache.clear()
    cache.clear()
    assert await cache.get_or_load("first", loader) == "new-first"
    assert await cache.get_or_load("second", loader) == "new-second"
    assert loader.await_count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidate_all", [False, True])
@pytest.mark.parametrize("old_load_fails", [False, True])
async def test_invalidated_inflight_load_cannot_replace_or_evict_new_result(
    cache: AsyncRequestCache[str, object], invalidate_all: bool, old_load_fails: bool,
) -> None:
    gate = ControlledLoader("old")

    async def load_old() -> object:
        value = await gate()
        if old_load_fails:
            raise ValueError("old load failed")
        return value

    leader = asyncio.create_task(cache.get_or_load("key", load_old))
    await wait_for_signal(gate.started)
    entered = asyncio.Event()
    waiter = asyncio.create_task(read_after_signalling(cache, "key", AsyncMock(), entered))
    await wait_for_signal(entered)
    if invalidate_all:
        cache.clear()
    else:
        cache.invalidate("key")
    fresh = AsyncMock(return_value="fresh")
    assert await cache.get_or_load("key", fresh) == "fresh"
    assert not leader.done()
    assert not waiter.done()
    gate.release.set()
    results = await asyncio.gather(leader, waiter, return_exceptions=True)
    if old_load_fails:
        assert all(isinstance(result, ValueError) for result in results)
    else:
        assert results == ["old", "old"]
    assert await cache.get_or_load("key", fresh) == "fresh"
    fresh.assert_awaited_once_with()
