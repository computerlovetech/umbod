import pytest
from pydantic import ValidationError

from umbod.core.responses import (
    OperationState,
    RetryAdvice,
    ToolArgumentIssue,
    ToolErrorDetails,
    ToolResponseMetadataFactory,
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", ""),
        ("code", "a" * 65),
        ("code", "invalid code"),
        ("code", "Invalid"),
        ("code", "invalid\n"),
        ("message", ""),
        ("message", "a" * 513),
    ],
)
def test_error_rejects_invalid_diagnostic_fields(
    error_details: ToolErrorDetails, field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        ToolErrorDetails.model_validate({**error_details.model_dump(), field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("field", "a" * 257),
        ("field", "arguments..name"),
        ("field", "arguments/name"),
        ("field", "arguments\n"),
        ("reason", ""),
        ("reason", "a" * 65),
        ("reason", "invalid reason"),
        ("reason", "Invalid"),
        ("correction", ""),
        ("correction", "a" * 257),
    ],
)
def test_issue_rejects_invalid_diagnostic_fields(
    argument_issue: ToolArgumentIssue, field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        ToolArgumentIssue.model_validate({**argument_issue.model_dump(), field: value})


def test_diagnostic_fields_accept_upper_bounds() -> None:
    issue = ToolArgumentIssue(field="a" * 256, reason="a" * 64, correction="a" * 256)
    error = ToolErrorDetails(code="a" * 64, message="a" * 512, issues=(issue,) * 8)

    assert len(error.issues) == 8


def test_global_error_has_no_issues() -> None:
    error = ToolErrorDetails(
        code="internal_error", message="Operation failed.", issues=()
    )

    assert error.issues == ()


def test_issue_allows_empty_path() -> None:
    issue = ToolArgumentIssue(
        field="", reason="invalid_arguments", correction="Correct arguments."
    )

    assert issue.field == ""


def test_error_rejects_more_than_eight_issues(
    argument_issue: ToolArgumentIssue,
) -> None:
    with pytest.raises(ValidationError, match="at most 8"):
        ToolErrorDetails(
            code="invalid_arguments",
            message="Correct arguments.",
            issues=(argument_issue,) * 9,
        )


@pytest.mark.parametrize("model_name", ["issue", "error"])
def test_diagnostics_require_every_field_and_reject_unknown_fields(
    argument_issue: ToolArgumentIssue,
    error_details: ToolErrorDetails,
    model_name: str,
) -> None:
    model = argument_issue if model_name == "issue" else error_details
    data = model.model_dump()
    for field in data:
        incomplete = {key: value for key, value in data.items() if key != field}
        with pytest.raises(ValidationError, match="Field required"):
            type(model).model_validate(incomplete)
    with pytest.raises(ValidationError, match="Extra inputs"):
        type(model).model_validate({**data, "unknown": "value"})


def test_nested_metadata_is_immutable(
    metadata_factory: ToolResponseMetadataFactory, error_details: ToolErrorDetails
) -> None:
    metadata = metadata_factory.failure(
        "request",
        error=error_details,
        operation_state=OperationState.NOT_STARTED,
        retry=RetryAdvice.NEVER,
        instructions=(),
        notices=(),
    )

    for model, field, value in (
        (metadata, "request_id", "changed"),
        (metadata.guidance.error, "message", "changed"),
        (metadata.guidance.error.issues[0], "correction", "changed"),
    ):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(model, field, value)
    assert isinstance(metadata.guidance.error.issues, tuple)


def test_success_metadata_is_immutable(
    metadata_factory: ToolResponseMetadataFactory,
) -> None:
    metadata = metadata_factory.success("request", notices=())

    with pytest.raises(ValidationError, match="frozen"):
        metadata.request_id = "changed"


def test_input_issue_list_is_copied_into_immutable_tuple(
    argument_issue: ToolArgumentIssue,
) -> None:
    issues = [argument_issue]
    error = ToolErrorDetails.model_validate(
        {"code": "invalid_arguments", "message": "Correct arguments.", "issues": issues}
    )
    issues.clear()

    assert error.issues == (argument_issue,)
