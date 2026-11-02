from typing import Any

import pytest
from fastmcp import Client

from .conftest import FilesystemMcp
from .test_tools import METADATA, root_id


NODE_ID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["create_filesystem_file", "create_filesystem_directory"])
@pytest.mark.parametrize("extra", [
    {"owner": "injected"}, {"caller": {}}, {"grants": []}, {"content": "SECRET"},
])
async def test_otherwise_valid_creation_rejects_authority_extras_without_creating_nodes(
    filesystem_invocation_mcp: FilesystemMcp, tool: str, extra: dict[str, Any],
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        parent = await root_id(client)
        captures_before = filesystem_invocation_mcp.callers.count
        result = await client.call_tool(tool, {
            "parent_id": parent, "name": "must-not-exist", "metadata": METADATA, **extra,
        }, raise_on_error=False)
        assert result.is_error
        assert filesystem_invocation_mcp.callers.count == captures_before
        children = await client.call_tool("list_filesystem_children", {"parent_id": parent})
        assert children.structured_content == {"nodes": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", [
    "get_filesystem_root", "get_filesystem_node", "list_filesystem_children",
])
@pytest.mark.parametrize("extra", [
    {"owner": "injected"}, {"caller": {}}, {"grants": []}, {"content": "SECRET"},
])
async def test_browsing_rejects_extras_before_invocation(
    filesystem_invocation_mcp: FilesystemMcp, tool: str, extra: dict[str, Any],
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        root = await root_id(client)
        arguments = {
            "get_filesystem_root": {},
            "get_filesystem_node": {"node_id": root},
            "list_filesystem_children": {"parent_id": root},
        }[tool]
        captures_before = filesystem_invocation_mcp.callers.count
        result = await client.call_tool(tool, {**arguments, **extra}, raise_on_error=False)
        assert result.is_error
        assert filesystem_invocation_mcp.callers.count == captures_before


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["create_filesystem_file", "create_filesystem_directory"])
@pytest.mark.parametrize("extra", [
    {"owner": "injected"}, {"caller": {}}, {"grants": []},
    {"content": "SECRET"}, {"key": "/private/path"},
])
async def test_creation_metadata_rejects_undeclared_fields(
    filesystem_invocation_mcp: FilesystemMcp, tool: str, extra: dict[str, Any],
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        parent = await root_id(client)
        captures_before = filesystem_invocation_mcp.callers.count
        result = await client.call_tool(tool, {
            "parent_id": parent, "name": "must-not-exist", "metadata": {**METADATA, **extra},
        }, raise_on_error=False)
        assert result.is_error
        assert filesystem_invocation_mcp.callers.count == captures_before
        children = await client.call_tool("list_filesystem_children", {"parent_id": parent})
        assert children.structured_content == {"nodes": []}


@pytest.mark.asyncio
async def test_authority_named_metadata_attributes_are_only_data(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        parent = await root_id(client)
        result = await client.call_tool("create_filesystem_file", {
            "parent_id": parent, "name": "ordinary",
            "metadata": {"content_type": {}, "attributes": {"owner": "bob", "key": "value"}},
        })
        assert result.structured_content["metadata"]["attributes"] == {"owner": "bob", "key": "value"}
        assert "owner" not in result.structured_content


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,arguments,field", [
    ("get_filesystem_root", {"SECRET_FIELD": "SECRET_VALUE"}, "arguments"),
    ("get_filesystem_node", {"node_id": "SECRET_VALUE"}, "node_id"),
    ("list_filesystem_children", {"parent_id": "SECRET_VALUE"}, "parent_id"),
    ("create_filesystem_file", {"parent_id": "SECRET_VALUE", "name": "private", "metadata": METADATA}, "parent_id"),
    ("create_filesystem_directory", {
        "parent_id": NODE_ID, "name": "private",
        "metadata": {"content_type": {}, "attributes": {"SECRET_FIELD": {"nested": "SECRET_VALUE"}}},
    }, "metadata.attributes"),
    ("filesystem_browse", {"operation": "tree", "target": {"type": "path", "path": "SECRET_VALUE"}}, "target.path"),
    ("filesystem_browse", {"operation": "SECRET_VALUE"}, "operation"),
    ("filesystem_browse", {"operation": "stat", "target": {"type": "SECRET_VALUE"}}, "target.type"),
    ("update_filesystem_node", {
        "node_id": NODE_ID, "expected_revision": 1,
        "metadata": {"attributes": {"SECRET_FIELD": {"nested": "SECRET_VALUE"}}},
    }, "metadata.attributes"),
    ("filesystem_upload", {
        "parent_id": "SECRET_VALUE", "name": "private", "metadata": METADATA,
        "content": {"encoding": "utf-8", "text": "SECRET_PAYLOAD"},
    }, "parent_id"),
    ("filesystem_upload", {
        "parent_id": NODE_ID, "name": "private", "metadata": METADATA,
        "content": {"encoding": "SECRET_VALUE", "text": "SECRET_PAYLOAD"},
    }, "content.encoding"),
    ("filesystem_begin_upload", {
        "parent_id": NODE_ID, "name": "private", "metadata": METADATA, "size_bytes": -1,
    }, "size_bytes"),
    ("filesystem_complete_upload", {"upload_id": "SECRET_VALUE"}, "upload_id"),
    ("filesystem_delete_file", {"node_id": NODE_ID, "expected_revision": True}, "expected_revision"),
    ("filesystem_search_sharing_recipients", {
        "node_id": NODE_ID, "query": "private", "recipient_type": "SECRET_VALUE",
    }, "recipient_type"),
    ("filesystem_share", {"node_id": NODE_ID, "group_id": "writers", "permissions": ["SECRET_VALUE"]}, "permissions"),
])
async def test_argument_errors_identify_safe_fields_without_echoing_input_or_performing_io(
    filesystem_invocation_mcp: FilesystemMcp, tool: str, arguments: dict[str, Any], field: str,
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str],
) -> None:
    captures = filesystem_invocation_mcp.callers.count
    async with Client(filesystem_invocation_mcp.server) as client:
        result = await client.call_tool(tool, arguments, raise_on_error=False)

    assert result.is_error
    assert field in result.content[0].text
    response_metadata = result.meta["computerlove.tech/umbod"]
    assert response_metadata["schema_version"] == 1
    assert response_metadata["guidance"]["outcome"] == "failure"
    assert response_metadata["guidance"]["operation_state"] == "not_started"
    assert response_metadata["guidance"]["recovery"]["retry"] == "after_correction"
    assert field in {issue["field"] for issue in response_metadata["guidance"]["error"]["issues"]}
    assert "input_value" not in result.content[0].text
    assert "ShareNodeCommand" not in result.content[0].text
    assert "function-after" not in result.content[0].text
    assert "SECRET" not in repr(result)
    assert "SECRET" not in caplog.text
    captured = capsys.readouterr()
    assert "SECRET" not in captured.out + captured.err
    assert filesystem_invocation_mcp.callers.count == captures
    assert filesystem_invocation_mcp.content.put_count == 0
