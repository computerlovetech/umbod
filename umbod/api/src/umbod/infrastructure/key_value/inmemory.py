from collections.abc import Hashable
from typing import Generic, TypeVar

from umbod.core.key_value import KeyValueHit, KeyValueMiss


KeyT = TypeVar("KeyT", bound=Hashable)
ValueT = TypeVar("ValueT")


class InMemoryKeyValueDriver(Generic[KeyT, ValueT]):
    def __init__(self) -> None:
        self._entries: dict[KeyT, ValueT] = {}

    async def get(self, key: KeyT) -> KeyValueHit[ValueT] | KeyValueMiss:
        try:
            value = self._entries[key]
        except KeyError:
            return KeyValueMiss()
        return KeyValueHit(value)

    async def set(self, key: KeyT, value: ValueT) -> None:
        self._entries[key] = value

    async def delete(self, key: KeyT) -> None:
        self._entries.pop(key, None)

    async def clear(self) -> None:
        self._entries.clear()
