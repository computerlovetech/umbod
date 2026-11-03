import pytest
from pydantic import ValidationError

from umbod.core.connectors.native.tools.descriptions import ConnectorToolDescription, MCP_TOOL_NAME_PATTERN


@pytest.mark.parametrize(
    "operation_name",
    [
        "echo",
        "get_default_response",
        "list_readable_channels",
        "user-profile/update",
        "admin.tools.list",
        "DATA_EXPORT_v2",
    ],
)
def test_connector_tool_description_accepts_mcp_compliant_operation_names(
    operation_name: str,
) -> None:
    description = ConnectorToolDescription(
        operation_name=operation_name, description="Example tool."
    )
    assert description.operation_name == operation_name


@pytest.mark.parametrize(
    "operation_name",
    [
        "",
        "has spaces",
        "comma,separated",
        "a" * 65,
        "invalid@name",
    ],
)
def test_connector_tool_description_rejects_non_mcp_compliant_operation_names(
    operation_name: str,
) -> None:
    with pytest.raises(ValidationError):
        ConnectorToolDescription(operation_name=operation_name, description="Example tool.")


def test_connector_tool_description_label_formats_operation_name() -> None:
    description = ConnectorToolDescription(
        operation_name="get_default_response", description="Example tool."
    )
    assert description.label == "Get default response"


def test_mcp_tool_name_pattern_matches_sep_986_examples() -> None:
    for name in ("getUser", "user-profile/update", "DATA_EXPORT_v2", "admin.tools.list"):
        assert MCP_TOOL_NAME_PATTERN.fullmatch(name)
