from collections.abc import Hashable
from typing import Protocol, TypeVar

from umbod.core.key_value.models import KeyValueHit, KeyValueMiss


KeyT_contra = TypeVar("KeyT_contra", bound=Hashable, contravariant=True)
ValueT = TypeVar("ValueT")


class KeyValueDriver(Protocol[KeyT_contra, ValueT]):
    async def get(self, key: KeyT_contra) -> KeyValueHit[ValueT] | KeyValueMiss: ...

    async def set(self, key: KeyT_contra, value: ValueT) -> None: ...

    async def delete(self, key: KeyT_contra) -> None: ...

    async def clear(self) -> None: ...
