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
    AllFields,
    UpsertCommand,
    InsertCommand,
)
from umbod.core.groups.models import (
    Group, RegisterGroupMetadata, UpdateGroupMetadata, GroupNotFound, GroupRevisionConflict,
)
from umbod.core.groups.ports import GroupCatalogueSession, GroupUsage
from .schema import GROUP_TABLE, GROUP_ID, PermissionGroupRecord, PermissionGroupKey
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
                GROUP_TABLE, Query(NoFilter(), AllFields(), Unordered())
            )
        return tuple(
            Group.model_validate(row.model_dump())
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

    async def register_metadata(self, request: RegisterGroupMetadata) -> None:
        await self._session.insert(
            GROUP_TABLE,
            InsertCommand(row=PermissionGroupRecord(**request.model_dump(), revision=1)),
        )

    async def update_metadata(self, group_id: str, request: UpdateGroupMetadata) -> Group:
        current = await self._session.find_one(
            GROUP_TABLE, Query(Equals(GROUP_ID, group_id), AllFields(), Unordered())
        )
        if current is None:
            raise GroupNotFound("Group not found")
        if current.revision != request.expected_revision:
            raise GroupRevisionConflict("Group metadata revision is stale")
        updated = PermissionGroupRecord(
            group_id=group_id, label=request.label, description=request.description,
            revision=current.revision + 1,
        )
        await self._session.upsert(
            GROUP_TABLE,
            UpsertCommand(key=PermissionGroupKey(group_id=group_id), row=updated),
        )
        return Group.model_validate(updated.model_dump())

    async def delete(self, group_id: str) -> None:
        await self._session.delete(GROUP_TABLE, DeleteQuery(Equals(GROUP_ID, group_id)))

    async def is_in_use(self, group_id: str) -> bool:
        return await self._usage.is_in_use(group_id)
