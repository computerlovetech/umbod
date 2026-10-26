from contextlib import AbstractAsyncContextManager
from typing import Protocol

from .models import Group


class GroupUsage(Protocol):
    async def is_in_use(self, group_id: str) -> bool: ...


class GroupCatalogueSession(GroupUsage, Protocol):
    async def register(self, group_id: str) -> None: ...

    async def delete(self, group_id: str) -> None: ...


class GroupCatalogue(Protocol):
    async def list_groups(self) -> tuple[Group, ...]: ...

    def write(self) -> AbstractAsyncContextManager[GroupCatalogueSession]: ...
