from collections.abc import Iterator
from contextlib import contextmanager

from fastmcp.exceptions import ToolError

from umbod.core.filesystem.authorization.errors import PermissionDenied
from umbod.core.filesystem.errors import (
    InvalidName,
    MissingNode,
    NameCollision,
    StorageFailure,
    WrongNodeKind,
)

_ERROR_MESSAGES: dict[type[Exception], str] = {
    PermissionDenied: "filesystem_permission_denied: Filesystem access denied",
    MissingNode: "filesystem_permission_denied: Filesystem access denied",
    InvalidName: "filesystem_invalid_name: Invalid filesystem name",
    NameCollision: "filesystem_name_collision: Filesystem name already exists",
    WrongNodeKind: "filesystem_wrong_node_kind: Invalid filesystem node kind",
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
