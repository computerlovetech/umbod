from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional, cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    AllFields, AllOf, Database, DatabaseSession, Equals, Field, InsertCommand, KeyCodec,
    PydanticJsonCodec, Query, RowCodec, Table, TableIdentity, TextCodec, TransactionMode, Unordered,
)
from ..homes.models import HomeBinding
from ..homes.ports import HomeTransaction
from ..models import Principal
from .access_control import SessionAccessControl
from .namespace import SessionNamespace
from .session import storage_session


class HomeKey(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issuer: str
    user_id: str


class HomeRecord(HomeKey):
    payload: HomeBinding


HOME_IDENTITY = TableIdentity("filesystem_homes")
HOME_ISSUER = Field[HomeRecord, str](HOME_IDENTITY, "issuer", TextCodec())
HOME_USER = Field[HomeRecord, str](HOME_IDENTITY, "user_id", TextCodec())
HOME_PAYLOAD = Field[HomeRecord, HomeBinding](HOME_IDENTITY, "payload", PydanticJsonCodec(HomeBinding))
HOME_TABLE = Table(
    HOME_IDENTITY,
    RowCodec(HomeRecord, cast(tuple[Field[HomeRecord, object], ...], (HOME_ISSUER, HOME_USER, HOME_PAYLOAD))),
    KeyCodec(HomeKey, cast(tuple[Field[HomeRecord, object], ...], (HOME_ISSUER, HOME_USER))),
)


class SessionHomes:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    async def get(self, user: Principal) -> Optional[HomeBinding]:
        record = await self._session.find_one(
            HOME_TABLE, Query(
                AllOf((Equals(HOME_ISSUER, user.issuer), Equals(HOME_USER, user.id))),
                AllFields(), Unordered(),
            ),
        )
        return record.payload if record is not None else None

    async def save(self, binding: HomeBinding) -> None:
        await self._session.insert(HOME_TABLE, InsertCommand(row=HomeRecord(
            issuer=binding.user.issuer, user_id=binding.user.id, payload=binding,
        )))


class DatabaseHomeTransactions:
    def __init__(self, database: Database) -> None:
        self._database = database

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[HomeTransaction]:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            namespace = SessionNamespace(session)
            await namespace.initialize_root()
            yield HomeTransaction(
                namespace=namespace, access_control=SessionAccessControl(session),
                homes=SessionHomes(session),
            )
