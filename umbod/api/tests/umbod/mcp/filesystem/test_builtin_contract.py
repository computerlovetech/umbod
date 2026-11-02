import pytest
from fastmcp import Client
from mcp.types import TextContent
from pydantic import TypeAdapter

from umbod.core.responses import ToolResponseMetadata
from umbod.mcp.responses.adapter import RESPONSE_METADATA_KEY

from .conftest import FilesystemMcp


_FILESYSTEM_TOOLS: tuple[str, ...] = (
    "filesystem_browse", "filesystem_upload", "filesystem_begin_upload", "filesystem_complete_upload",
    "update_filesystem_node", "filesystem_delete_file", "filesystem_search_sharing_recipients",
    "filesystem_share", "get_filesystem_root", "get_filesystem_node", "list_filesystem_children",
    "create_filesystem_file", "create_filesystem_directory",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", _FILESYSTEM_TOOLS)
async def test_every_filesystem_builtin_uses_the_common_response_contract(
    filesystem_invocation_mcp: FilesystemMcp, tool_name: str,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool(tool_name, {}, raise_on_error=False)

    metadata = TypeAdapter(ToolResponseMetadata).validate_python(result.meta[RESPONSE_METADATA_KEY])
    visible = "\n".join(block.text for block in result.content if isinstance(block, TextContent))

    assert metadata.schema_version == 1
    assert metadata.guidance.outcome == ("failure" if result.is_error else "success")
    assert f"Outcome: {metadata.guidance.outcome}" in visible
    assert f"Operation state: {metadata.guidance.operation_state}" in visible
    assert f"Retry advice: {metadata.guidance.recovery.retry}" in visible
    for instruction in metadata.guidance.recovery.instructions:
        assert instruction in visible
