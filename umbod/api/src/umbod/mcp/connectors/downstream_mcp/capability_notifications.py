import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar


ChangeResult = TypeVar("ChangeResult")


class NativeCapabilityProjection(Protocol):
    async def native_capability_projection(
        self,
    ) -> tuple[tuple[object, ...], tuple[object, ...]]: ...


class CapabilityListChangeNotifier(Protocol):
    def notify_tool_list_changed(self) -> bool: ...

    def notify_prompt_list_changed(self) -> bool: ...

    def notify_resource_list_changed(self) -> bool: ...


class NativeCapabilityChangeMonitor:
    def __init__(
        self,
        projection: NativeCapabilityProjection,
        notifier: CapabilityListChangeNotifier,
    ) -> None:
        self._projection = projection
        self._notifier = notifier
        self._baseline: tuple[tuple[object, ...], tuple[object, ...]] = ((), ())
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lock:
            self._baseline = await self._projection.native_capability_projection()

    async def apply_and_notify(
        self,
        change: Callable[[], Awaitable[ChangeResult]],
    ) -> ChangeResult:
        async with self._lock:
            previous = await self._projection.native_capability_projection()
            result = await change()
            current = await self._projection.native_capability_projection()
            self._baseline = current
            self._notify_changes(previous, current)
            return result

    async def reconcile(self) -> None:
        async with self._lock:
            current = await self._projection.native_capability_projection()
            previous = self._baseline
            self._baseline = current
            self._notify_changes(previous, current)

    def notify_tool_list_changed(self) -> bool:
        return self._notifier.notify_tool_list_changed()

    def _notify_changes(
        self,
        previous: tuple[tuple[object, ...], tuple[object, ...]],
        current: tuple[tuple[object, ...], tuple[object, ...]],
    ) -> None:
        if previous[0] != current[0]:
            self._notifier.notify_prompt_list_changed()
        if previous[1] != current[1]:
            self._notifier.notify_resource_list_changed()
