import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine

import pytest_asyncio

from umbod.core.caching import AsyncRequestCache


class OwnedTasks:
    def __init__(self) -> None:
        self.tasks: list[asyncio.Task[object]] = []

    def create(self, coroutine: Coroutine[object, object, object]) -> asyncio.Task[object]:
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task

    async def results(self, *tasks: asyncio.Task[object], return_exceptions: bool) -> list[object]:
        return await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=return_exceptions), timeout=2,
        )

    async def close(self) -> None:
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await self.results(*self.tasks, return_exceptions=True)


@pytest_asyncio.fixture
async def owned_tasks() -> AsyncIterator[OwnedTasks]:
    tasks = OwnedTasks()
    try:
        yield tasks
    finally:
        await tasks.close()


class ControlledLoader:
    def __init__(self, value: object) -> None:
        self.value = value
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def __call__(self) -> object:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return self.value


async def read_after_signalling(
    cache: AsyncRequestCache[str, object], key: str,
    loader: Callable[[], Awaitable[object]], entered: asyncio.Event,
) -> object:
    entered.set()
    return await cache.get_or_load(key, loader)


async def wait_for_signal(signal: asyncio.Event) -> None:
    await asyncio.wait_for(signal.wait(), timeout=2)
