import pytest
from mcp.types import Tool

from umbod.core.connectors.downstream_mcp.adapters.tool_mapping import bind_tool, map_sdk_tool


@pytest.mark.parametrize("output_schema", (None, {}, {"type": "object"}))
def test_sdk_tool_mapping_preserves_complete_metadata_and_output_presence(output_schema: dict[str, object] | None) -> None:
    sdk_tool = Tool.model_validate({
        "name": "read",
        "title": "Private title",
        "description": "Private description",
        "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}},
        "outputSchema": output_schema,
        "annotations": {"title": "Annotated title", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        "icons": [{"src": "https://example.org/icon.svg", "mimeType": "image/svg+xml", "sizes": ["32x32"]}],
        "_meta": {"private": {"owner": "alice"}},
        "execution": {"taskSupport": "forbidden"},
    })
    capability = map_sdk_tool(sdk_tool)
    tool = bind_tool("personal", capability)
    assert tool.identity.connector_id == "personal"
    assert tool.identity.downstream_name == "read"
    assert tool.title == "Private title"
    assert tool.description == "Private description"
    assert tool.input_schema == sdk_tool.input_schema
    assert tool.annotations == {"title": "Annotated title", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    assert tool.icons == ({"src": "https://example.org/icon.svg", "mimeType": "image/svg+xml", "sizes": ["32x32"]},)
    assert tool.meta == {"private": {"owner": "alice"}}
    assert tool.execution == {"taskSupport": "forbidden"}
    if output_schema is None:
        assert tool.output_schema_status == "absent"
    else:
        assert tool.output_schema_status == "present"
        assert tool.output_schema == output_schema
