from contextlib import contextmanager
from typing import Any, Iterator

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from umbod.core.permissions import (
    ConnectorToolPermission,
    InMemoryGroupConnectorToolPermissions,
)
from tests.umbod.mcp.connectors.tools.test_connector_tool_exposure_mode_acceptance import (
    ConnectorToolExposureMcpBuilder,
)


@contextmanager
def authenticated_groups(group_ids: tuple[str, ...]) -> Iterator[None]:
    marker = auth_context_var.set(
        AuthenticatedUser(
            AccessToken(
                token="test-context-token",
                client_id="client",
                scopes=[],
                claims={"groups": list(group_ids)},
            )
        )
    )
    try:
        yield
    finally:
        auth_context_var.reset(marker)


async def _search_description(mcp: Any) -> str:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    return next(tool.description for tool in tools if tool.name == "search_tools") or ""


async def _search(mcp: Any) -> list[dict[str, object]]:
    async with Client(mcp) as client:
        result = await client.call_tool("search_tools", {"query": "readable channels"})
    return result.structured_content["matches"]


@pytest.mark.asyncio
async def test_gateway_search_excludes_tool_not_authorized_for_authenticated_group() -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.replace_group_permissions({"engineering": ()}, {"engineering": ()})
    builder = ConnectorToolExposureMcpBuilder().in_gateway_mode().with_permissions(permissions)
    mcp = await builder.build()

    with authenticated_groups(("engineering",)):
        matches = await _search(mcp)

    assert "slack_list_readable_channels" not in {match["tool_name"] for match in matches}


@pytest.mark.asyncio
async def test_gateway_manifest_is_request_local_without_cross_principal_leakage() -> None:
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
    with authenticated_groups(("engineering",)):
        engineering_description = await _search_description(mcp)
    with authenticated_groups(("guests",)):
        guest_description = await _search_description(mcp)
    with authenticated_groups(("engineering",)):
        repeated_engineering_description = await _search_description(mcp)

    assert "Slack: Access connector capabilities. (1 operations)" in engineering_description
    assert "Slack" not in guest_description
    assert repeated_engineering_description == engineering_description


@pytest.mark.asyncio
async def test_gateway_direct_execution_denies_tool_not_authorized_for_authenticated_group() -> None:
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
    with authenticated_groups(("engineering",)):
        async with Client(mcp) as client:
            with pytest.raises(ToolError, match="Unknown tool"):
                await client.call_tool(
                    "execute_tool",
                    {"tool_name": "slack_list_readable_channels", "arguments": {}},
                )

    assert executed == []


@pytest.mark.asyncio
async def test_gateway_permission_grant_becomes_searchable_and_executable_without_restart() -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    builder = ConnectorToolExposureMcpBuilder().in_gateway_mode().with_permissions(permissions)
    mcp = await builder.build()
    with authenticated_groups(("engineering",)):
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
async def test_gateway_permission_revoke_removes_search_and_denies_previously_discovered_name() -> None:
    permissions = InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",))
    permissions.replace_group_permissions(
        {"engineering": ("slack",)},
        {"engineering": (ConnectorToolPermission("slack", "list_readable_channels"),)},
    )
    builder = ConnectorToolExposureMcpBuilder().in_gateway_mode().with_permissions(permissions)
    mcp = await builder.build()
    with authenticated_groups(("engineering",)):
        assert {match["tool_name"] for match in await _search(mcp)} == {"slack_list_readable_channels"}

        permissions.replace_group_permissions({"engineering": ()}, {"engineering": ()})

        assert await _search(mcp) == []
        async with Client(mcp) as client:
            with pytest.raises(ToolError, match="Unknown tool"):
                await client.call_tool(
                    "execute_tool",
                    {"tool_name": "slack_list_readable_channels", "arguments": {}},
                )
