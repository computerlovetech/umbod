from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from umbod.core.filesystem import InvalidName, NameCollision, StorageFailure, WrongNodeKind
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.content import UploadTooLarge


@contextmanager
def filesystem_errors() -> Iterator[None]:
    try:
        yield
    except PermissionDenied:
        raise HTTPException(403, detail={
            "code": "filesystem_permission_denied",
            "message": "Filesystem access denied.",
        }) from None
    except UploadTooLarge:
        raise HTTPException(413, detail={
            "code": "filesystem_upload_too_large",
            "message": "Upload exceeds the configured size limit.",
        }) from None
    except InvalidName:
        raise HTTPException(422, detail={
            "code": "filesystem_invalid_name",
            "message": "Invalid filesystem name.",
        }) from None
    except NameCollision:
        raise HTTPException(409, detail={
            "code": "filesystem_name_collision",
            "message": "Filesystem name already exists.",
        }) from None
    except WrongNodeKind:
        raise HTTPException(409, detail={
            "code": "filesystem_wrong_node_kind",
            "message": "Invalid filesystem node kind.",
        }) from None
    except StorageFailure:
        raise HTTPException(500, detail={
            "code": "filesystem_storage_failure",
            "message": "Filesystem operation failed.",
        }) from None
