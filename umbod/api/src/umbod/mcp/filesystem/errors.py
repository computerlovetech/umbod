from collections.abc import Iterator
from contextlib import contextmanager

from fastmcp.exceptions import ToolError

from umbod.core.filesystem.authorization.errors import PermissionDenied
from umbod.core.filesystem.content.errors import UploadTooLarge
from umbod.core.filesystem.uploads.errors import (
    UploadConflict, UploadExpired, UploadLengthMismatch, UploadMediaTypeMismatch,
)
from umbod.core.filesystem.errors import (
    InvalidName,
    MissingNode,
    NameCollision,
    RevisionConflict,
    StorageFailure,
    WrongNodeKind,
)

class ReadTooLarge(Exception):
    pass


class InvalidReadEncoding(Exception):
    pass


_ERROR_MESSAGES: dict[type[Exception], str] = {
    ReadTooLarge: "filesystem_read_too_large: Filesystem file exceeds read limit",
    InvalidReadEncoding: "filesystem_read_invalid_encoding: File is not valid UTF-8; use base64",
    UploadTooLarge: "filesystem_upload_too_large: Filesystem upload too large",
    UploadConflict: "filesystem_upload_conflict: Filesystem upload conflict",
    UploadExpired: "filesystem_upload_expired: Filesystem upload expired",
    UploadLengthMismatch: "filesystem_upload_length_mismatch: Invalid upload length",
    UploadMediaTypeMismatch: "filesystem_upload_media_type_mismatch: Invalid upload content type",
    PermissionDenied: "filesystem_permission_denied: Filesystem access denied",
    MissingNode: "filesystem_permission_denied: Filesystem access denied",
    InvalidName: "filesystem_invalid_name: Invalid filesystem name",
    NameCollision: "filesystem_name_collision: Filesystem name already exists",
    WrongNodeKind: "filesystem_wrong_node_kind: Invalid filesystem node kind",
    RevisionConflict: "filesystem_revision_conflict: Filesystem revision conflict",
    StorageFailure: "filesystem_storage_failure: Filesystem storage unavailable",
}


@contextmanager
def filesystem_operation() -> Iterator[None]:
    try:
        yield
    except Exception as error:
        for error_type, message in _ERROR_MESSAGES.items():
            if isinstance(error, error_type):
                raise ToolError(message) from None
        raise ToolError("filesystem_operation_failed: Filesystem operation failed") from None
