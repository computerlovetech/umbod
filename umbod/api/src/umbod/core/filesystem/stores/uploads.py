from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import (
    AllFields, Database, DatabaseSession, Equals, Field, KeyCodec, PydanticJsonCodec,
    Query, RowCodec, Table, TableIdentity, TextCodec, TransactionMode, Unordered, UpsertCommand,
)
from ..uploads.models import UploadSession
from ..uploads.ports import UploadTransaction
from .access_control import SessionAccessControl
from .namespace import SessionNamespace
from .session import storage_session


class UploadKey(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    upload_id: str


class UploadRecord(UploadKey):
    payload: UploadSession


UPLOAD_IDENTITY = TableIdentity("filesystem_uploads")
UPLOAD_ID = Field[UploadRecord, str](UPLOAD_IDENTITY, "upload_id", TextCodec())
UPLOAD_PAYLOAD = Field[UploadRecord, UploadSession](
    UPLOAD_IDENTITY, "payload", PydanticJsonCodec(UploadSession),
)
UPLOAD_TABLE = Table(
    UPLOAD_IDENTITY,
    RowCodec(UploadRecord, cast(tuple[Field[UploadRecord, object], ...], (UPLOAD_ID, UPLOAD_PAYLOAD))),
    KeyCodec(UploadKey, cast(tuple[Field[UploadRecord, object], ...], (UPLOAD_ID,))),
)


class SessionUploads:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    async def get(self, upload_id: UUID) -> Optional[UploadSession]:
        record = await self._session.find_one(
            UPLOAD_TABLE, Query(Equals(UPLOAD_ID, str(upload_id)), AllFields(), Unordered()),
        )
        return record.payload if record is not None else None

    async def save(self, upload: UploadSession) -> None:
        await self._session.upsert(UPLOAD_TABLE, UpsertCommand(
            key=UploadKey(upload_id=str(upload.id)),
            row=UploadRecord(upload_id=str(upload.id), payload=upload),
        ))


class DatabaseUploadTransactions:
    def __init__(self, database: Database) -> None:
        self._database = database

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[UploadTransaction]:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            namespace = SessionNamespace(session)
            await namespace.initialize_root()
            yield UploadTransaction(
                namespace=namespace, access_control=SessionAccessControl(session),
                uploads=SessionUploads(session),
            )
