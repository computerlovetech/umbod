import pytest

from umbod.core.administrator.connector_configuration import (
    ConfigurationConflict,
    ConfigurationError,
    ConfigurationRejected,
)
from umbod.core.responses import RetryAdvice
from umbod.mcp.administrator.errors import configuration_rejection_error
from umbod.mcp.tools.errors import BuiltinToolError


@pytest.mark.parametrize(
    "code,expected_code,field",
    [
        ("connector_not_found", "connector_not_found", "connector_id"),
        ("capability_not_found", "capability_not_found", "desired_state.operations"),
        ("revision_conflict", "revision_conflict", "desired_state.operations"),
        ("duplicate_target", "duplicate_target", "desired_state.operations"),
        ("private_unknown_code", "configuration_rejected", ""),
        ("revision_conflict_private_target", "configuration_rejected", ""),
    ],
)
def test_rejection_exposes_only_approved_static_details(
    code: str, expected_code: str, field: str,
) -> None:
    result = ConfigurationRejected(
        error=ConfigurationError(code=code, message="private_connector private_capability"),
        conflicts=(ConfigurationConflict(
            target="private_target", expected_revision=139, current_revision=952,
        ),),
    )

    error = configuration_rejection_error(result)

    assert isinstance(error, BuiltinToolError)
    assert error.details.code == expected_code
    assert str(error) == error.details.message
    assert error.retry == RetryAdvice.AFTER_CORRECTION
    assert tuple(issue.field for issue in error.details.issues) == ((field,) if field else ())
    assert all(issue.correction for issue in error.details.issues)
    public_details = error.details.model_dump_json()
    assert "private_" not in public_details
    assert "139" not in public_details
    assert "952" not in public_details
