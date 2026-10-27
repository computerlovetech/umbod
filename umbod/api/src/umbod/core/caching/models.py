from collections.abc import Hashable
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID


KeyT = TypeVar("KeyT", bound=Hashable)


@dataclass(frozen=True)
class CacheStorageKey(Generic[KeyT]):
    namespace: UUID
    key: KeyT
    generation: UUID
