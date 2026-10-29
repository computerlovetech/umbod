from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from asyncio import Lock

from umbod.core.groups.models import Group
from umbod.core.groups.ports import GroupCatalogueSession, GroupUsage


class InMemoryGroupCatalogue:
    def __init__(self, usage: GroupUsage) -> None:
        self._usage = usage
        self._groups: set[str] = set()
        self._lock = Lock()

    async def list_groups(self) -> tuple[Group, ...]:
        return tuple(Group(group_id=value) for value in sorted(self._groups))

    @asynccontextmanager
    async def write(self) -> AsyncIterator[GroupCatalogueSession]:
        async with self._lock:
            previous = self._groups.copy()
            try:
                yield self
            except BaseException:
                self._groups = previous
                raise

    async def register(self, group_id: str) -> None:
        self._groups.add(group_id)

    async def delete(self, group_id: str) -> None:
        self._groups.discard(group_id)

    async def is_in_use(self, group_id: str) -> bool:
        return await self._usage.is_in_use(group_id)
