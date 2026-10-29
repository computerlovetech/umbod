from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol
from uuid import UUID

from ..transactions import FilesystemSession
from .models import UploadSession


class UploadStore(Protocol):
    async def get(self, upload_id: UUID) -> Optional[UploadSession]: ...

    async def save(self, upload: UploadSession) -> None: ...


@dataclass(frozen=True)
class UploadTransaction(FilesystemSession):
    uploads: UploadStore


class UploadTransactions(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[UploadTransaction]: ...


class UploadClock(Protocol):
    def now(self) -> datetime: ...
