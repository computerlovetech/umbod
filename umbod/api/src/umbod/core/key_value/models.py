from dataclasses import dataclass
from typing import Generic, TypeVar


ValueT = TypeVar("ValueT")


@dataclass(frozen=True)
class KeyValueMiss:
    pass


@dataclass(frozen=True)
class KeyValueHit(Generic[ValueT]):
    value: ValueT
