from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from umbod.core.persistence import Database, DatabaseSession, TransactionMode
from ..authorization.errors import PermissionDenied
from ..sharing.errors import InvalidSharingPolicy, SharingPolicyUnavailable
from ..content.errors import UploadTooLarge
from ..uploads.errors import UploadSessionError
from ..errors import PolicyConflict, PolicyRevisionConflict, PolicyUnavailable
from ..namespaces.errors import NamespaceActiveUploads, NamespaceNotEmpty, NamespaceNotFound, NamespaceValidationError
from ..errors import (
    InvalidMove,
    RootMutation,
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
        InvalidSharingPolicy,
        SharingPolicyUnavailable,
        UploadTooLarge,
        UploadSessionError,
        PolicyConflict,
        PolicyUnavailable,
        NamespaceActiveUploads,
        NamespaceNotEmpty,
        NamespaceNotFound,
        NamespaceValidationError,
        PolicyRevisionConflict,
        InvalidMove,
        RootMutation,
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
