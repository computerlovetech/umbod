from types import SimpleNamespace
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from umbod.core.permissions import (
    ConnectorToolPermission,
    InMemoryGroupConnectorToolPermissions,
)
from tests.umbod.mcp.connectors.tools.test_connector_tool_exposure_mode_acceptance import (
    ConnectorToolExposureMcpBuilder,
)


async def _search_description(mcp: Any) -> str:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    return next(tool.description for tool in tools if tool.name == "search_tools") or ""


async def _search(mcp: Any) -> list[dict[str, object]]:
    async with Client(mcp) as client:
        result = await client.call_tool("search_tools", {"query": "readable channels"})
    return result.structured_content["matches"]


@pytest.mark.asyncio
async def test_gateway_search_excludes_tool_not_authorized_for_authenticated_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.replace_group_permissions({"engineering": ()}, {"engineering": ()})
    builder = ConnectorToolExposureMcpBuilder().in_gateway_mode().with_permissions(permissions)
    mcp = await builder.build()

    monkeypatch.setattr(
        "umbod.mcp.connectors.tools.infrastructure.dependencies.get_access_token",
        lambda: SimpleNamespace(claims={"groups": ["engineering"]}),
    )

    matches = await _search(mcp)

    assert "slack_list_readable_channels" not in {match["tool_name"] for match in matches}


@pytest.mark.asyncio
async def test_gateway_manifest_is_request_local_without_cross_principal_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.replace_group_permissions(
        {"engineering": ("slack",), "guests": ()},
        {
            "engineering": (ConnectorToolPermission("slack", "list_readable_channels"),),
            "guests": (),
        },
    )
    mcp = (
        await ConnectorToolExposureMcpBuilder()
        .in_gateway_mode()
        .with_permissions(permissions)
        .build()
    )
    active_groups = ["engineering"]
    monkeypatch.setattr(
        "umbod.mcp.connectors.tools.infrastructure.dependencies.get_access_token",
        lambda: SimpleNamespace(claims={"groups": active_groups}),
    )

    engineering_description = await _search_description(mcp)
    active_groups[:] = ["guests"]
    guest_description = await _search_description(mcp)
    active_groups[:] = ["engineering"]
    repeated_engineering_description = await _search_description(mcp)

    assert "Slack: Access connector capabilities. (1 operations)" in engineering_description
    assert "Slack" not in guest_description
    assert repeated_engineering_description == engineering_description


@pytest.mark.asyncio
async def test_gateway_direct_execution_denies_tool_not_authorized_for_authenticated_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[bool] = []

    def operation() -> dict[str, object]:
        executed.append(True)
        return {"ok": True}

    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.replace_group_permissions({"engineering": ()}, {"engineering": ()})
    builder = (
        ConnectorToolExposureMcpBuilder()
        .in_gateway_mode()
        .with_operation(operation)
        .with_permissions(permissions)
    )
    mcp = await builder.build()
    monkeypatch.setattr(
        "umbod.mcp.connectors.tools.infrastructure.dependencies.get_access_token",
        lambda: SimpleNamespace(claims={"groups": ["engineering"]}),
    )

    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool(
                "execute_tool",
                {"tool_name": "slack_list_readable_channels", "arguments": {}},
            )

    assert executed == []


@pytest.mark.asyncio
async def test_gateway_permission_grant_becomes_searchable_and_executable_without_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    builder = ConnectorToolExposureMcpBuilder().in_gateway_mode().with_permissions(permissions)
    mcp = await builder.build()
    monkeypatch.setattr(
        "umbod.mcp.connectors.tools.infrastructure.dependencies.get_access_token",
        lambda: SimpleNamespace(claims={"groups": ["engineering"]}),
    )
    assert await _search(mcp) == []

    permissions.replace_group_permissions(
        {"engineering": ("slack",)},
        {"engineering": (ConnectorToolPermission("slack", "list_readable_channels"),)},
    )

    assert {match["tool_name"] for match in await _search(mcp)} == {"slack_list_readable_channels"}
    async with Client(mcp) as client:
        result = await client.call_tool(
            "execute_tool",
            {"tool_name": "slack_list_readable_channels", "arguments": {}},
        )
    assert result.is_error is False


@pytest.mark.asyncio
async def test_gateway_permission_revoke_removes_search_and_denies_previously_discovered_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.replace_group_permissions(
        {"engineering": ("slack",)},
        {"engineering": (ConnectorToolPermission("slack", "list_readable_channels"),)},
    )
    builder = ConnectorToolExposureMcpBuilder().in_gateway_mode().with_permissions(permissions)
    mcp = await builder.build()
    monkeypatch.setattr(
        "umbod.mcp.connectors.tools.infrastructure.dependencies.get_access_token",
        lambda: SimpleNamespace(claims={"groups": ["engineering"]}),
    )
    assert {match["tool_name"] for match in await _search(mcp)} == {"slack_list_readable_channels"}

    permissions.replace_group_permissions({"engineering": ()}, {"engineering": ()})

    assert await _search(mcp) == []
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="Unknown tool"):
            await client.call_tool(
                "execute_tool",
                {"tool_name": "slack_list_readable_channels", "arguments": {}},
            )
