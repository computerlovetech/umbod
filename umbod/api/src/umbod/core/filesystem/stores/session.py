from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from umbod.core.persistence import Database, DatabaseSession, TransactionMode
from ..authorization.errors import PermissionDenied
from ..content.errors import UploadTooLarge
from ..uploads.errors import UploadSessionError
from ..administration.errors import PolicyConflict, PolicyRevisionConflict
from ..errors import (
    ProvisioningConflict,
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
        PermissionDenied,
        UploadTooLarge,
        UploadSessionError,
        PolicyConflict,
        PolicyRevisionConflict,
        ProvisioningConflict,
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
