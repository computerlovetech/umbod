import pytest
from fastmcp.exceptions import ResourceError

from umbod.core.filesystem.authorization.errors import PermissionDenied
from umbod.core.filesystem.content.errors import UploadTooLarge
from umbod.core.filesystem.errors import (
    InvalidMove, InvalidName, MissingNode, NameCollision, PolicyDecodingFailure,
    RevisionConflict, RootMutation, StorageFailure, WrongNodeKind,
)
from umbod.core.filesystem.sharing import InvalidSharingPolicy, SharingPolicyUnavailable
from umbod.core.filesystem.uploads.errors import (
    UploadChecksumMismatch, UploadConflict, UploadExpired, UploadLengthMismatch,
    UploadMediaTypeMismatch, UploadReceiptUnavailable,
)
from umbod.core.responses import OperationState, RetryAdvice
from umbod.mcp.filesystem.approval_state import FileDeletionApprovalDenied
from umbod.mcp.filesystem.errors import (
    InvalidReadEncoding, ReadTooLarge, filesystem_operation, filesystem_preflight, filesystem_resource_operation,
)
from umbod.mcp.responses.progress import operation_completed, operation_progress_context
from umbod.mcp.tools.errors import BuiltinToolAuthorizationDenied, BuiltinToolError, BuiltinToolRejected


@pytest.mark.parametrize("error_type", [
    InvalidSharingPolicy, ReadTooLarge, InvalidReadEncoding, UploadTooLarge,
    UploadChecksumMismatch, UploadReceiptUnavailable, UploadConflict, UploadExpired,
    UploadLengthMismatch, UploadMediaTypeMismatch, InvalidMove, RootMutation,
    InvalidName, NameCollision, WrongNodeKind, RevisionConflict,
])
def test_preflight_expected_domain_failures_are_builtin_tool_rejections(error_type: type[Exception]) -> None:
    with operation_progress_context() as progress:
        with pytest.raises(BuiltinToolRejected) as caught:
            with filesystem_preflight():
                raise error_type("SECRET /private/path")
        assert progress.state is OperationState.NOT_STARTED
    assert isinstance(caught.value, BuiltinToolError)
    assert "SECRET" not in str(caught.value)
    assert "/private/path" not in caught.value.details.model_dump_json()


@pytest.mark.parametrize("error_type", [
    StorageFailure, PolicyDecodingFailure, SharingPolicyUnavailable, RuntimeError,
])
def test_preflight_server_faults_are_not_builtin_tool_rejections(error_type: type[Exception]) -> None:
    with operation_progress_context() as progress:
        with pytest.raises(BuiltinToolError) as caught:
            with filesystem_preflight():
                raise error_type("SECRET /private/path")
        assert progress.state is OperationState.NOT_STARTED
    assert not isinstance(caught.value, BuiltinToolRejected)
    assert "SECRET" not in str(caught.value)
    assert "/private/path" not in caught.value.details.model_dump_json()


@pytest.mark.parametrize(
    ("error_type", "code", "retry"),
    [
        (InvalidName, "filesystem_invalid_name", RetryAdvice.AFTER_CORRECTION),
        (NameCollision, "filesystem_name_collision", RetryAdvice.AFTER_CORRECTION),
        (RevisionConflict, "filesystem_revision_conflict", RetryAdvice.AFTER_CORRECTION),
        (StorageFailure, "filesystem_storage_failure", RetryAdvice.INSPECT_BEFORE_RETRY),
        (UploadConflict, "filesystem_upload_conflict", RetryAdvice.INSPECT_BEFORE_RETRY),
        (UploadReceiptUnavailable, "filesystem_upload_receipt_unavailable", RetryAdvice.INSPECT_BEFORE_RETRY),
        (SharingPolicyUnavailable, "filesystem_policy_unavailable", RetryAdvice.NEVER),
        (RuntimeError, "filesystem_operation_failed", RetryAdvice.INSPECT_BEFORE_RETRY),
    ],
)
def test_domain_failure_details_are_static_and_progress_is_conservative(
    error_type: type[Exception], code: str, retry: RetryAdvice,
) -> None:
    with operation_progress_context() as progress:
        with pytest.raises(BuiltinToolError) as caught:
            with filesystem_operation():
                raise error_type("SECRET /private/path")
        assert progress.state is OperationState.UNKNOWN
    failure = caught.value
    assert failure.details.code == code
    assert failure.retry is retry
    assert failure.details.issues == ()
    assert str(failure).startswith(code + ": " + failure.details.message)
    assert "SECRET" not in failure.details.model_dump_json()
    assert "/private/path" not in str(failure)


@pytest.mark.parametrize(("error_type", "retry"), [
    (PermissionDenied, RetryAdvice.AFTER_PERMISSION_CHANGE),
    (MissingNode, RetryAdvice.AFTER_PERMISSION_CHANGE),
    (FileDeletionApprovalDenied, RetryAdvice.NEVER),
])
def test_authorization_failures_distinguish_permission_from_human_approval(
    error_type: type[Exception], retry: RetryAdvice,
) -> None:
    with pytest.raises(BuiltinToolAuthorizationDenied) as caught:
        with filesystem_operation():
            raise error_type("SECRET")
    assert caught.value.retry is retry
    assert "SECRET" not in caught.value.details.model_dump_json()


def test_missing_and_inaccessible_nodes_have_identical_details() -> None:
    failures: list[BuiltinToolAuthorizationDenied] = []
    for error_type in (MissingNode, PermissionDenied):
        with pytest.raises(BuiltinToolAuthorizationDenied) as caught:
            with filesystem_operation():
                raise error_type("SECRET")
        failures.append(caught.value)
    assert failures[0].details == failures[1].details
    assert str(failures[0]) == str(failures[1])


def test_post_commit_failure_preserves_completed_progress() -> None:
    with operation_progress_context() as progress:
        with pytest.raises(BuiltinToolError):
            with filesystem_operation():
                operation_completed()
                raise StorageFailure("SECRET")
        assert progress.state is OperationState.COMPLETED


@pytest.mark.parametrize("error_type", [MissingNode, PermissionDenied, StorageFailure, RuntimeError])
def test_resource_errors_remain_resource_errors_without_tool_progress(error_type: type[Exception]) -> None:
    with operation_progress_context() as progress:
        with pytest.raises(ResourceError) as caught:
            with filesystem_resource_operation():
                raise error_type("SECRET")
        assert progress.state is OperationState.NOT_STARTED
    assert "SECRET" not in str(caught.value)
