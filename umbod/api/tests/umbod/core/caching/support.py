import asyncio
from collections.abc import Awaitable, Callable

from umbod.core.caching import AsyncRequestCache


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
