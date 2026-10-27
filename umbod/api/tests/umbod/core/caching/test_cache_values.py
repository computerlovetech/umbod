import asyncio
from unittest.mock import AsyncMock

import pytest

from umbod.core.caching import AsyncRequestCache, RecursiveCacheLoadError
from umbod.infrastructure import create_request_cache


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, False, 0, "", (), [], {}, object()])
async def test_successful_values_are_reused_without_calling_later_loaders(
    cache: AsyncRequestCache[str, object], value: object,
) -> None:
    loader = AsyncMock(return_value=value)
    unused = AsyncMock()
    assert await cache.get_or_load("key", loader) is value
    assert await cache.get_or_load("key", unused) is value
    loader.assert_awaited_once_with()
    unused.assert_not_awaited()


@pytest.mark.asyncio
async def test_distinct_instances_do_not_share_results(cache: AsyncRequestCache[str, object]) -> None:
    other: AsyncRequestCache[str, object] = create_request_cache()
    assert await cache.get_or_load("same", AsyncMock(return_value="first")) == "first"
    assert await other.get_or_load("same", AsyncMock(return_value="second")) == "second"


@pytest.mark.asyncio
async def test_compound_hashable_keys_keep_operation_scopes_separate() -> None:
    cache: AsyncRequestCache[tuple[str, str], int] = create_request_cache()
    loader = AsyncMock(side_effect=[1, 2])
    assert await cache.get_or_load(("first-owner", "query"), loader) == 1
    assert await cache.get_or_load(("second-owner", "query"), loader) == 2
    assert await cache.get_or_load(("first-owner", "query"), loader) == 1
    assert loader.await_count == 2


@pytest.mark.asyncio
async def test_failure_is_propagated_and_next_call_retries(cache: AsyncRequestCache[str, object]) -> None:
    loader = AsyncMock(side_effect=[ValueError("unavailable"), "recovered"])
    with pytest.raises(ValueError, match="unavailable"):
        await cache.get_or_load("key", loader)
    assert await cache.get_or_load("key", loader) == "recovered"
    assert await cache.get_or_load("key", loader) == "recovered"
    assert loader.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("indirect", [False, True])
async def test_same_task_recursive_loads_fail_instead_of_deadlocking(
    cache: AsyncRequestCache[str, object], indirect: bool,
) -> None:
    async def load_second() -> object:
        return await cache.get_or_load("first", load_first)

    async def load_first() -> object:
        if indirect:
            return await cache.get_or_load("second", load_second)
        return await cache.get_or_load("first", load_first)

    with pytest.raises(RecursiveCacheLoadError):
        await asyncio.wait_for(cache.get_or_load("first", load_first), timeout=2)
    assert await cache.get_or_load("first", AsyncMock(return_value="retry")) == "retry"
    assert await cache.get_or_load("second", AsyncMock(return_value="retry")) == "retry"


@pytest.mark.asyncio
async def test_loader_runs_in_initiating_task(cache: AsyncRequestCache[str, object]) -> None:
    initiating_task = asyncio.current_task()

    async def load() -> object:
        return asyncio.current_task() is initiating_task

    assert await cache.get_or_load("key", load) is True
