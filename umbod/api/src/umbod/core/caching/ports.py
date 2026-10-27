from collections.abc import Awaitable, Callable, Hashable
from typing import Protocol, TypeVar


KeyT_contra = TypeVar("KeyT_contra", bound=Hashable, contravariant=True)
ValueT = TypeVar("ValueT")


class AsyncRequestCache(Protocol[KeyT_contra, ValueT]):
    async def get_or_load(
        self, key: KeyT_contra, loader: Callable[[], Awaitable[ValueT]],
    ) -> ValueT: ...

    def invalidate(self, key: KeyT_contra) -> None: ...

    def clear(self) -> None: ...
