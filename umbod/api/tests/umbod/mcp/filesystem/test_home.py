from typing import Any

import pytest
from fastmcp import Client
from jsonschema import ValidationError, validate

from umbod.core.callers import AuthenticationProvenance
from .conftest import FilesystemMcp, caller_snapshot
from .test_visibility import listed_tools, select_caller


@pytest.mark.asyncio
async def test_targetless_home_resolves_private_upload_destination_and_reconciles_tools(
    filesystem_mcp: FilesystemMcp,
) -> None:
    select_caller(filesystem_mcp, "new-user")
    assert await listed_tools(filesystem_mcp) == {"filesystem_browse"}
    async with Client(filesystem_mcp.server) as client:
        descriptor = next(tool for tool in await client.list_tools() if tool.name == "filesystem_browse")
        validate({"operation": "home"}, descriptor.input_schema)
        first = await client.call_tool("filesystem_browse", {"operation": "home"})
        repeated = await client.call_tool("filesystem_browse", {"operation": "home"})
        assert first.structured_content == repeated.structured_content
        validate(first.structured_content, descriptor.output_schema)
        result = first.structured_content["result"]
        node = result["node"]
        assert node["permissions"]["can_write"] is True
        assert node["permissions"]["can_delete"] is False
        assert node["visible_to"]["type"] == "available"
        assert node["visible_to"]["grants"] == []
        assert '"can_write":true' in first.content[0].text
        assert 'visible_to={"type":"available","scope":"direct_node_policy"' in first.content[0].text
        assert '"grants":[]' in first.content[0].text
        assert result["breadcrumbs"]["complete"] is False
        listing = await client.call_tool("filesystem_browse", {
            "operation": "ls", "target": {"type": "node", "node_id": node["id"]},
        })
        assert listing.structured_content["result"]["entries"] == []
    await filesystem_mcp.runtime.reconcile()
    tools = await listed_tools(filesystem_mcp)
    assert "filesystem_begin_upload" in tools
    assert "get_filesystem_root" not in tools
    assert len(await filesystem_mcp.server.list_tools()) <= 13
    assert "upload it to Umbod" in descriptor.description
    assert "original-byte" in descriptor.description


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [
    {"target": {"type": "root"}}, {"user": "mallory"}, {"issuer": "other"}, {"user_id": "mallory"},
])
async def test_home_rejects_target_and_supplied_identity(
    filesystem_mcp: FilesystemMcp, extra: dict[str, Any],
) -> None:
    async with Client(filesystem_mcp.server) as client:
        descriptor = next(tool for tool in await client.list_tools() if tool.name == "filesystem_browse")
        with pytest.raises(ValidationError):
            validate({"operation": "home", **extra}, descriptor.input_schema)
        response = await client.call_tool("filesystem_browse", {"operation": "home", **extra}, raise_on_error=False)
    assert response.is_error


@pytest.mark.asyncio
async def test_home_invocation_rechecks_verified_identity(filesystem_invocation_mcp: FilesystemMcp) -> None:
    filesystem_invocation_mcp.callers.current.set(caller_snapshot(
        "alice", "https://issuer", (), AuthenticationProvenance.LOCAL_TEST,
    ))
    async with Client(filesystem_invocation_mcp.server) as client:
        response = await client.call_tool("filesystem_browse", {"operation": "home"}, raise_on_error=False)
    assert response.is_error
    assert "filesystem_permission_denied" in response.content[0].text
