from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from umbod.core.persistence import Database, DatabaseSession, TransactionMode
from ..errors import (
    InvalidName,
    MissingNode,
    NameCollision,
    OwnershipNotFound,
    RevisionConflict,
    StorageFailure,
    WrongNodeKind,
)


@asynccontextmanager
async def storage_session(
    database: Database, mode: TransactionMode
) -> AsyncIterator[DatabaseSession]:
    try:
        async with database.session(mode=mode) as session:
            yield session
    except (
        InvalidName,
        MissingNode,
        NameCollision,
        OwnershipNotFound,
        RevisionConflict,
        WrongNodeKind,
        StorageFailure,
    ):
        raise
    except Exception as error:
        raise StorageFailure("Filesystem persistence failed") from error
