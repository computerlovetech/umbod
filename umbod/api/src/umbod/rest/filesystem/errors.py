from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from umbod.core.filesystem import InvalidName, NameCollision, StorageFailure, WrongNodeKind
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.errors import InvalidMove, RevisionConflict, RootMutation
from umbod.core.filesystem.sharing import InvalidSharingPolicy, SharingPolicyUnavailable
from umbod.core.filesystem.content import UploadTooLarge
from umbod.core.filesystem.uploads.errors import (
    UploadChecksumMismatch, UploadConflict, UploadExpired, UploadLengthMismatch, UploadMediaTypeMismatch,
)


@contextmanager
def filesystem_errors() -> Iterator[None]:
    try:
        yield
    except PermissionDenied:
        raise HTTPException(403, detail={
            "code": "filesystem_permission_denied",
            "message": "Filesystem access denied.",
        }) from None
    except InvalidSharingPolicy:
        raise HTTPException(422, detail={
            "code": "filesystem_sharing_invalid", "message": "Invalid filesystem sharing policy.",
        }) from None
    except SharingPolicyUnavailable:
        raise HTTPException(503, detail={
            "code": "filesystem_policy_unavailable", "message": "Filesystem policy is unavailable.",
        }) from None
    except UploadTooLarge:
        raise HTTPException(413, detail={
            "code": "filesystem_upload_too_large",
            "message": "Upload exceeds the configured size limit.",
        }) from None
    except UploadExpired:
        raise HTTPException(410, detail={
            "code": "filesystem_upload_expired", "message": "Upload session expired.",
        }) from None
    except UploadConflict:
        raise HTTPException(409, detail={
            "code": "filesystem_upload_conflict", "message": "Upload is not in the required state.",
        }) from None
    except UploadChecksumMismatch:
        raise HTTPException(422, detail={
            "code": "filesystem_upload_checksum_mismatch", "message": "Upload checksum does not match.",
        }) from None
    except UploadLengthMismatch:
        raise HTTPException(422, detail={
            "code": "filesystem_upload_length_mismatch", "message": "Upload length does not match declared size.",
        }) from None
    except UploadMediaTypeMismatch:
        raise HTTPException(415, detail={
            "code": "filesystem_upload_media_type", "message": "Upload content type does not match metadata.",
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
    except InvalidMove:
        raise HTTPException(409, detail={
            "code": "filesystem_invalid_move",
            "message": "Invalid filesystem destination.",
        }) from None
    except RootMutation:
        raise HTTPException(409, detail={
            "code": "filesystem_root_protected",
            "message": "The filesystem root cannot be renamed or moved.",
        }) from None
    except RevisionConflict:
        raise HTTPException(412, detail={
            "code": "filesystem_revision_conflict",
            "message": "Filesystem revision does not match.",
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
