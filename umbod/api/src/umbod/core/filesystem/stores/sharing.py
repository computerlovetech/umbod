from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from umbod.core.groups.models import Group
from umbod.core.groups.stores.schema import GROUP_ID_PROJECTION, GROUP_TABLE
from umbod.core.persistence import (
    AllFields, Database, DatabaseSession, NoFilter, Query, TransactionMode, Unordered,
)

from ..models import AccessGrant
from ..ports import AccessControlDriver, NamespaceDriver
from ..sharing.ports import RegisteredGroupReader, SharingGrantWriter, SharingSession
from .access_control import SessionAccessControl
from .namespace import SessionNamespace
from .session import storage_session


class SessionRegisteredGroups:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    async def registered_groups(self) -> tuple[Group, ...]:
        records = await self._session.find_many(
            GROUP_TABLE,
            Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
        )
        return tuple(Group.model_validate(record.model_dump()) for record in records)

    async def registered_group_ids(self) -> frozenset[str]:
        records = await self._session.find_many(
            GROUP_TABLE,
            Query(filter=NoFilter(), projection=GROUP_ID_PROJECTION, ordering=Unordered()),
        )
        return frozenset(record.group_id for record in records)


class SessionSharingGrants:
    def __init__(self, access_control: SessionAccessControl) -> None:
        self._access_control = access_control

    async def upsert(self, grant: AccessGrant) -> None:
        await self._access_control.upsert_registered_grant(grant)


@dataclass(frozen=True)
class DatabaseSharingSession:
    namespace: NamespaceDriver
    access_control: AccessControlDriver
    groups: RegisteredGroupReader
    grants: SharingGrantWriter


class DatabaseSharingTransactions:
    def __init__(self, database: Database) -> None:
        self._database = database

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SharingSession]:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            access_control = SessionAccessControl(session)
            yield DatabaseSharingSession(
                namespace=SessionNamespace(session),
                access_control=access_control,
                groups=SessionRegisteredGroups(session),
                grants=SessionSharingGrants(access_control),
            )
