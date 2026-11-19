from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from umbod.core.persistence import Database, TransactionMode

from ..transactions import FilesystemReadSession, FilesystemSession
from ..errors import StorageFailure
from .access_control import SessionAccessControl, SessionAccessReader
from .namespace import SessionNamespace, SessionNodeReader
from .session import storage_session


class DatabaseFilesystemTransactions:
    def __init__(self, database: Database) -> None:
        self._database = database

    @asynccontextmanager
    async def read(self) -> AsyncIterator[FilesystemReadSession]:
        try:
            async with self._database.read_session() as session:
                yield FilesystemReadSession(SessionNodeReader(session), SessionAccessReader(session))
        except StorageFailure:
            raise
        except Exception as error:
            raise StorageFailure("Filesystem access read failed") from error

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with storage_session(self._database, TransactionMode.SERIALIZED_WRITE) as session:
            namespace = SessionNamespace(session)
            await namespace.initialize_root()
            yield FilesystemSession(
                namespace=namespace, access_control=SessionAccessControl(session)
            )
