import pytest

from umbod.core.responses import (
    ToolArgumentIssue,
    ToolErrorDetails,
    ToolResponseMetadataFactory,
)


@pytest.fixture
def metadata_factory() -> ToolResponseMetadataFactory:
    return ToolResponseMetadataFactory(
        server_version="1.2.3", server_revision="revision"
    )


@pytest.fixture
def argument_issue() -> ToolArgumentIssue:
    return ToolArgumentIssue(
        field="arguments.items.0.name",
        reason="required",
        correction="Supply a name.",
    )


@pytest.fixture
def error_details(argument_issue: ToolArgumentIssue) -> ToolErrorDetails:
    return ToolErrorDetails(
        code="invalid_arguments",
        message="Correct the supplied arguments.",
        issues=(argument_issue,),
    )
