from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from umbod.core.persistence import (
    Database,
    DatabaseSession,
    TransactionMode,
    Query,
    NoFilter,
    Unordered,
    DeleteQuery,
    Equals,
)
from umbod.core.groups.models import Group
from umbod.core.groups.ports import GroupCatalogueSession, GroupUsage
from .schema import GROUP_TABLE, GROUP_ID, GROUP_ID_PROJECTION
from .registration import register_group_in_session


class DatabaseGroupCatalogue:
    def __init__(
        self, database: Database, usage_factory: Callable[[DatabaseSession], GroupUsage]
    ) -> None:
        self._database = database
        self._usage_factory = usage_factory

    async def list_groups(self) -> tuple[Group, ...]:
        async with self._database.session(mode=TransactionMode.READ_WRITE) as session:
            rows = await session.find_many(
                GROUP_TABLE, Query(NoFilter(), GROUP_ID_PROJECTION, Unordered())
            )
        return tuple(
            Group(group_id=row.group_id)
            for row in sorted(rows, key=lambda row: row.group_id)
        )

    @asynccontextmanager
    async def write(self) -> AsyncIterator[GroupCatalogueSession]:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            yield DatabaseGroupCatalogueSession(session, self._usage_factory(session))


class DatabaseGroupCatalogueSession:
    def __init__(self, session: DatabaseSession, usage: GroupUsage) -> None:
        self._session = session
        self._usage = usage

    async def register(self, group_id: str) -> None:
        await register_group_in_session(self._session, group_id)

    async def delete(self, group_id: str) -> None:
        await self._session.delete(GROUP_TABLE, DeleteQuery(Equals(GROUP_ID, group_id)))

    async def is_in_use(self, group_id: str) -> bool:
        return await self._usage.is_in_use(group_id)
