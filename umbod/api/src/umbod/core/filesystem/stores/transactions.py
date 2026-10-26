from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from umbod.core.persistence import Database, TransactionMode

from ..transactions import FilesystemSession
from .access_control import SessionAccessControl
from .namespace import SessionNamespace
from .session import storage_session


class DatabaseFilesystemTransactions:
    def __init__(self, database: Database) -> None:
        self._database = database

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            namespace = SessionNamespace(session)
            await namespace.initialize_root()
            yield FilesystemSession(
                namespace=namespace, access_control=SessionAccessControl(session)
            )
