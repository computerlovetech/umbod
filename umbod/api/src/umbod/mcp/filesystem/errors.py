from collections.abc import Iterator
from contextlib import contextmanager

from fastmcp.exceptions import AuthorizationError, ResourceError
from mcp.shared.exceptions import MCPError

from umbod.core.responses import RetryAdvice, ToolErrorDetails
from umbod.mcp.responses.progress import operation_started
from umbod.mcp.tools.errors import (
    BuiltinToolApprovalDenied, BuiltinToolAuthorizationDenied, BuiltinToolError, BuiltinToolRejected,
)

from .approval_state import FileDeletionApprovalDenied

from umbod.core.filesystem.authorization.errors import PermissionDenied
from umbod.core.filesystem.sharing import InvalidSharingPolicy, SharingPolicyUnavailable
from umbod.core.filesystem.content.errors import UploadTooLarge
from umbod.core.filesystem.uploads.errors import (
    UploadChecksumMismatch, UploadConflict, UploadExpired, UploadLengthMismatch, UploadMediaTypeMismatch,
    UploadReceiptUnavailable,
)
from umbod.core.filesystem.errors import (
    InvalidMove,
    RootMutation,
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


FILESYSTEM_ACCESS_DENIED = "filesystem_permission_denied: Filesystem access denied. Choose an accessible node or ask its owner for the required permissions. Creating files requires discover and write on the parent directory; filesystem_browse with operation home resolves your private upload destination."


_ERROR_MESSAGES: dict[type[Exception], str] = {
    InvalidSharingPolicy: "filesystem_invalid_sharing_policy: Invalid filesystem sharing policy. Select valid recipients and permissions, then retry.",
    SharingPolicyUnavailable: "filesystem_policy_unavailable: Filesystem sharing configuration unavailable. Ask an administrator to check the sharing configuration.",
    ReadTooLarge: "filesystem_read_too_large: Filesystem file exceeds read limit. Use an authorized HTTP download instead of resources/read.",
    InvalidReadEncoding: "filesystem_read_invalid_encoding: File is not valid UTF-8. Use an authorized HTTP download to retrieve the original bytes.",
    UploadTooLarge: "filesystem_upload_too_large: Filesystem upload too large. Use filesystem_begin_upload for files above the 10 MiB inline limit; the configured server limit still applies.",
    UploadChecksumMismatch: "filesystem_upload_checksum_mismatch: Upload checksum does not match. Compute SHA256 from the original bytes and begin a new upload with the correct checksum.",
    UploadReceiptUnavailable: "filesystem_upload_receipt_unavailable: Legacy upload has no verified receipt. Check whether the destination file already exists before starting another upload.",
    UploadConflict: "filesystem_upload_conflict: Filesystem upload conflict. Check the upload state before retrying; do not blindly begin another upload.",
    UploadExpired: "filesystem_upload_expired: Filesystem upload expired. Begin a new upload, transfer the bytes, and complete it before expiry.",
    UploadLengthMismatch: "filesystem_upload_length_mismatch: Invalid upload length. Compute size_bytes from the original bytes and transfer exactly that many bytes.",
    UploadMediaTypeMismatch: "filesystem_upload_media_type_mismatch: Invalid upload content type. Send the Content-Type specified by the upload transfer instructions.",
    InvalidMove: "filesystem_invalid_move: Invalid filesystem destination. Choose a directory outside the node's own subtree.",
    RootMutation: "filesystem_root_protected: The filesystem root cannot be renamed or moved. Select a non-root node.",
    InvalidName: "filesystem_invalid_name: Invalid filesystem name. Use a nonempty UTF-8 name other than . or .., without slashes, backslashes, or null characters.",
    NameCollision: "filesystem_name_collision: Filesystem name already exists. Inspect the existing node before retrying, or choose a different name.",
    WrongNodeKind: "filesystem_wrong_node_kind: Invalid filesystem node kind. Inspect the node and select the file or directory required by this operation.",
    RevisionConflict: "filesystem_revision_conflict: Filesystem revision conflict. Read the current node, review its changes, and retry with its current revision.",
    StorageFailure: "filesystem_storage_failure: Filesystem storage unavailable. A write may have completed; check the destination before retrying. If this persists, contact the administrator with the request ID and server version.",
}


@contextmanager
def filesystem_resource_operation() -> Iterator[None]:
    try:
        yield
    except (PermissionDenied, MissingNode):
        raise ResourceError(FILESYSTEM_ACCESS_DENIED) from None
    except Exception as error:
        for error_type, message in _ERROR_MESSAGES.items():
            if isinstance(error, error_type):
                raise ResourceError(message) from None
        raise ResourceError("filesystem_operation_failed: Filesystem operation failed. A write may have completed; check the destination before retrying. If this persists, contact the administrator with the request ID and server version.") from None


_OPERATION_FAILED = "filesystem_operation_failed: Filesystem operation failed. A write may have completed; check the destination before retrying. If this persists, contact the administrator with the request ID and server version."
_DELETION_APPROVAL_DENIED = "filesystem_delete_approval_denied: File deletion requires explicit human approval"


def _details(message: str) -> ToolErrorDetails:
    code, summary = message.split(": ", 1)
    return ToolErrorDetails(code=code, message=summary, issues=())


_ERROR_DETAILS = {error_type: _details(message) for error_type, message in _ERROR_MESSAGES.items()}
_TOOL_ACCESS_DENIED = "filesystem_permission_denied: Filesystem access denied. Choose an accessible node or ask its owner for the required permissions."
_ACCESS_DENIED_DETAILS = _details(_TOOL_ACCESS_DENIED)
_ERROR_DETAILS.update({
    StorageFailure: _details("filesystem_storage_failure: Filesystem storage unavailable."),
    UploadConflict: _details("filesystem_upload_conflict: Filesystem upload conflict."),
    UploadExpired: _details("filesystem_upload_expired: Filesystem upload expired."),
    UploadChecksumMismatch: _details("filesystem_upload_checksum_mismatch: Upload checksum does not match."),
    UploadLengthMismatch: _details("filesystem_upload_length_mismatch: Invalid upload length."),
    UploadReceiptUnavailable: _details("filesystem_upload_receipt_unavailable: Legacy upload has no verified receipt."),
})
_DELETION_APPROVAL_DETAILS = _details(_DELETION_APPROVAL_DENIED)
_OPERATION_FAILED_DETAILS = _details("filesystem_operation_failed: Filesystem operation failed.")
_ERROR_RETRIES = {
    SharingPolicyUnavailable: RetryAdvice.NEVER,
    UploadReceiptUnavailable: RetryAdvice.INSPECT_BEFORE_RETRY,
    UploadConflict: RetryAdvice.INSPECT_BEFORE_RETRY,
    StorageFailure: RetryAdvice.INSPECT_BEFORE_RETRY,
}


@contextmanager
def filesystem_operation() -> Iterator[None]:
    with filesystem_preflight():
        operation_started()
        yield


@contextmanager
def filesystem_preflight() -> Iterator[None]:
    try:
        yield
    except (MCPError, AuthorizationError):
        raise
    except FileDeletionApprovalDenied:
        raise BuiltinToolApprovalDenied(
            _DELETION_APPROVAL_DENIED, details=_DELETION_APPROVAL_DETAILS,
        ) from None
    except (PermissionDenied, MissingNode):
        raise BuiltinToolAuthorizationDenied(
            _TOOL_ACCESS_DENIED, details=_ACCESS_DENIED_DETAILS,
        ) from None
    except Exception as error:
        for error_type, message in _ERROR_MESSAGES.items():
            if isinstance(error, error_type):
                failure_type = BuiltinToolError if error_type in (StorageFailure, SharingPolicyUnavailable) else BuiltinToolRejected
                raise failure_type(
                    message, details=_ERROR_DETAILS[error_type],
                    retry=_ERROR_RETRIES.get(error_type, RetryAdvice.AFTER_CORRECTION),
                ) from None
        raise BuiltinToolError(
            _OPERATION_FAILED, details=_OPERATION_FAILED_DETAILS,
            retry=RetryAdvice.INSPECT_BEFORE_RETRY,
        ) from None
