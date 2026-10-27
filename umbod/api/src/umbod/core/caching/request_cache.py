import asyncio
from collections.abc import Awaitable, Callable, Hashable
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from umbod.core.caching.errors import RecursiveCacheLoadError
from umbod.core.caching.models import CacheStorageKey
from umbod.core.key_value import KeyValueDriver, KeyValueHit


KeyT = TypeVar("KeyT", bound=Hashable)
ValueT = TypeVar("ValueT")


class RequestCache(Generic[KeyT, ValueT]):
    def __init__(self, driver: KeyValueDriver[CacheStorageKey[KeyT], ValueT]) -> None:
        self._driver = driver
        self._namespace = uuid4()
        self._generations: dict[KeyT, UUID] = {}
        self._pending: dict[KeyT, asyncio.Future[ValueT]] = {}
        self._owners: dict[asyncio.Future[ValueT], asyncio.Task[object]] = {}

    async def get_or_load(
        self, key: KeyT, loader: Callable[[], Awaitable[ValueT]],
    ) -> ValueT:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Request cache loads require an asyncio task")
        try:
            entry = self._pending[key]
        except KeyError:
            return await self._load(key, loader, task)
        if self._owners.get(entry) is task:
            raise RecursiveCacheLoadError("A loader cannot recursively load its own cache key")
        return await asyncio.shield(entry)

    def _storage_key(self, key: KeyT) -> CacheStorageKey[KeyT]:
        try:
            generation = self._generations[key]
        except KeyError:
            generation = uuid4()
            self._generations[key] = generation
        return CacheStorageKey(namespace=self._namespace, key=key, generation=generation)

    async def _read_or_load(
        self, key: KeyT, entry: asyncio.Future[ValueT], loader: Callable[[], Awaitable[ValueT]],
    ) -> ValueT:
        storage_key = self._storage_key(key)
        cached = await self._driver.get(storage_key)
        if isinstance(cached, KeyValueHit):
            return cached.value
        value = await loader()
        if self._pending.get(key) is entry:
            await self._driver.set(storage_key, value)
        return value

    async def _load(
        self, key: KeyT, loader: Callable[[], Awaitable[ValueT]], task: asyncio.Task[object],
    ) -> ValueT:
        entry: asyncio.Future[ValueT] = asyncio.get_running_loop().create_future()
        self._pending[key] = entry
        self._owners[entry] = task
        try:
            value = await self._read_or_load(key, entry, loader)
        except BaseException as error:
            if self._pending.get(key) is entry:
                self._generations.pop(key, None)
            if isinstance(error, asyncio.CancelledError):
                entry.cancel()
            else:
                entry.set_exception(error)
                entry.exception()
            raise
        else:
            entry.set_result(value)
            return value
        finally:
            if self._pending.get(key) is entry:
                del self._pending[key]
            del self._owners[entry]

    def invalidate(self, key: KeyT) -> None:
        self._pending.pop(key, None)
        self._generations.pop(key, None)

    def clear(self) -> None:
        self._pending.clear()
        self._generations.clear()
