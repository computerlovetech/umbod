from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from asyncio import Lock

from umbod.core.groups.models import (
    Group, RegisterGroupMetadata, UpdateGroupMetadata, GroupNotFound, GroupRevisionConflict,
)
from umbod.core.groups.ports import GroupCatalogueSession, GroupUsage


class InMemoryGroupCatalogue:
    def __init__(self, usage: GroupUsage) -> None:
        self._usage = usage
        self._groups: dict[str, Group] = {}
        self._lock = Lock()

    async def list_groups(self) -> tuple[Group, ...]:
        return tuple(self._groups[value] for value in sorted(self._groups))

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
        self._groups.setdefault(group_id, Group(group_id=group_id, label=group_id, description="", revision=1))

    async def register_metadata(self, request: RegisterGroupMetadata) -> None:
        self._groups.setdefault(request.group_id, Group(**request.model_dump(), revision=1))

    async def update_metadata(self, group_id: str, request: UpdateGroupMetadata) -> Group:
        if group_id not in self._groups:
            raise GroupNotFound("Group not found")
        current = self._groups[group_id]
        if current.revision != request.expected_revision:
            raise GroupRevisionConflict("Group metadata revision is stale")
        updated = Group(group_id=group_id, label=request.label, description=request.description, revision=current.revision + 1)
        self._groups[group_id] = updated
        return updated

    async def delete(self, group_id: str) -> None:
        self._groups.pop(group_id, None)

    async def is_in_use(self, group_id: str) -> bool:
        return await self._usage.is_in_use(group_id)
