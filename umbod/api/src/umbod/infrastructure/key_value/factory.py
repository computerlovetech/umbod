from collections.abc import Hashable
from typing import TypeVar

from umbod.core.caching import AsyncRequestCache, RequestCache
from umbod.core.key_value import KeyValueDriver


KeyT = TypeVar("KeyT", bound=Hashable)
ValueT = TypeVar("ValueT")


def create_inmemory_key_value_driver() -> KeyValueDriver[KeyT, ValueT]:
    from umbod.infrastructure.key_value.inmemory import InMemoryKeyValueDriver

    return InMemoryKeyValueDriver[KeyT, ValueT]()


def create_request_cache() -> AsyncRequestCache[KeyT, ValueT]:
    from umbod.core.caching.models import CacheStorageKey

    driver: KeyValueDriver[CacheStorageKey[KeyT], ValueT] = (
        create_inmemory_key_value_driver()
    )
    return RequestCache[KeyT, ValueT](driver)
