import json
from unittest.mock import Mock

import pytest
from fastmcp import Client

from umbod.core.responses import ToolFailureMetadata
from umbod.mcp.responses.adapter import BuiltinToolResponseAdapter, RESPONSE_METADATA_KEY

from .conftest import FilesystemMcp
from .test_tools import METADATA, root_id
from .test_visibility import select_caller


@pytest.mark.parametrize("tool_name", ["create_filesystem_file", "create_filesystem_directory"])
@pytest.mark.asyncio
async def test_create_response_failure_reports_completed_without_duplicate_write(
    filesystem_invocation_mcp: FilesystemMcp, tool_name: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = filesystem_invocation_mcp
    async with Client(filesystem.server) as client:
        parent = await root_id(client)
        with monkeypatch.context() as patches:
            preparation = Mock(side_effect=RuntimeError("SECRET response payload"))
            patches.setattr(BuiltinToolResponseAdapter, "prepare", preparation)
            result = await client.call_tool(tool_name, {
                "parent_id": parent, "name": "file", "metadata": METADATA,
            }, raise_on_error=False)
        children = await client.call_tool("list_filesystem_children", {"parent_id": parent})
    assert result.is_error
    validated = ToolFailureMetadata.model_validate(result.meta[RESPONSE_METADATA_KEY])
    assert validated.schema_version == 1
    assert validated.request_id
    assert validated.guidance.outcome == "failure"
    assert validated.guidance.operation_state == "completed"
    assert validated.guidance.recovery.retry == "inspect_before_retry"
    assert validated.guidance.error.issues == ()
    assert "SECRET" not in json.dumps({
        "meta": result.meta, "content": [item.model_dump(mode="json") for item in result.content],
        "structured_content": result.structured_content,
    })
    assert [node["name"] for node in children.structured_content["nodes"]] == ["file"]
    preparation.assert_called_once()


@pytest.mark.asyncio
async def test_home_response_failure_retains_completed_provisioning(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = filesystem_invocation_mcp
    select_caller(filesystem, "new-home-user")
    async with Client(filesystem.server) as client:
        with monkeypatch.context() as patches:
            preparation = Mock(side_effect=RuntimeError("SECRET home response"))
            patches.setattr(BuiltinToolResponseAdapter, "prepare", preparation)
            result = await client.call_tool("filesystem_browse", {"operation": "home"}, raise_on_error=False)
        first = await client.call_tool("filesystem_browse", {"operation": "namespaces"})
        recovered = await client.call_tool("filesystem_browse", {"operation": "home"})
        repeated = await client.call_tool("filesystem_browse", {"operation": "namespaces"})
    validated = ToolFailureMetadata.model_validate(result.meta[RESPONSE_METADATA_KEY])
    assert validated.guidance.operation_state == "completed"
    assert validated.guidance.recovery.retry == "inspect_before_retry"
    assert "SECRET" not in repr(result)
    assert first.structured_content == repeated.structured_content
    namespaces = first.structured_content["result"]["namespaces"]
    assert len(namespaces) == 1
    assert namespaces[0]["root_node_id"] == recovered.structured_content["result"]["node"]["id"]
    preparation.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["filesystem_share", "filesystem_search_sharing_recipients"])
async def test_sharing_response_failure_retains_completed_operation_without_duplicate_grants(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch, tool_name: str,
) -> None:
    filesystem = filesystem_invocation_mcp
    async with Client(filesystem.server) as client:
        created = await client.call_tool("create_filesystem_file", {
            "parent_id": await root_id(client), "name": "shared-file", "metadata": METADATA,
        })
        node_id = created.structured_content["id"]
        arguments = (
            {"node_id": node_id, "group_id": "writers", "permissions": ["discover", "read"]}
            if tool_name == "filesystem_share" else {"node_id": node_id, "query": "writers"}
        )
        with monkeypatch.context() as patches:
            preparation = Mock(side_effect=RuntimeError("SECRET sharing response"))
            patches.setattr(BuiltinToolResponseAdapter, "prepare", preparation)
            failed = await client.call_tool(tool_name, arguments, raise_on_error=False)
        current = await client.call_tool("get_filesystem_node", {"node_id": node_id})
    assert failed.is_error
    guidance = ToolFailureMetadata.model_validate(failed.meta[RESPONSE_METADATA_KEY]).guidance
    assert guidance.operation_state == "completed"
    assert guidance.recovery.retry == "inspect_before_retry"
    assert "SECRET" not in repr(failed)
    grants = current.structured_content["sharing"]["grants"]
    assert len(grants) == (1 if tool_name == "filesystem_share" else 0)
    if grants:
        assert grants[0]["recipient"]["group_id"] == "writers"
        assert grants[0]["permissions"] == ["discover", "read"]
    preparation.assert_called_once()
