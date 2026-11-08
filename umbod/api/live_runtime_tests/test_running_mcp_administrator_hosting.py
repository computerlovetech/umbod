import os
import ssl
from typing import Any

import httpx
import pytest

from conftest import RuntimeEndpoints
from test_running_personal_mcp_execution import mcp_client, proxy_token

ADMINISTRATOR_TOOLS = {
    "read_connector_configuration",
    "upsert_connector_configuration",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", sorted(ADMINISTRATOR_TOOLS))
async def test_verified_administrator_tools_remain_authorized_only_on_administrator_endpoint(
    runtime_endpoints: RuntimeEndpoints, tool_name: str,
) -> None:
    member_bearer = os.environ.get("UMBOD_TEST_MEMBER_BEARER_TOKEN")
    if not member_bearer:
        pytest.skip("Requires the verified-user runtime stage")
    arguments: dict[str, Any] = {"connector_kind": "native", "connector_id": "test"}
    if tool_name == "upsert_connector_configuration":
        arguments["desired_state"] = {"operations": []}
    context = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(
        base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=context, timeout=30,
    ) as identity:
        administrator_token = proxy_token(
            runtime_endpoints.admin_mcp_url, runtime_endpoints.bearer_token, identity,
        )
        async with mcp_client(runtime_endpoints.admin_mcp_url, administrator_token) as administrator:
            names = {tool.name for tool in await administrator.list_tools()}
            if runtime_endpoints.admin_mcp_url != runtime_endpoints.mcp_url:
                assert names == ADMINISTRATOR_TOOLS
            else:
                assert ADMINISTRATOR_TOOLS <= names
            result = await administrator.call_tool(tool_name, arguments)
            assert result.is_error is False
            assert result.structured_content["connector"] == {
                "connector_kind": "native", "connector_id": "test",
            }
            assert result.meta["computerlove.tech/umbod"]["guidance"]["outcome"] == "success"

        if runtime_endpoints.admin_mcp_url != runtime_endpoints.mcp_url:
            public_token = proxy_token(
                runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, identity,
            )
            async with mcp_client(runtime_endpoints.mcp_url, public_token) as public:
                assert not ADMINISTRATOR_TOOLS & {tool.name for tool in await public.list_tools()}
                denied = await public.call_tool(tool_name, arguments, raise_on_error=False)
                assert denied.is_error is True
                assert denied.content[0].text == (
                    f"Authorization failed for tool '{tool_name}': not found or not authorized"
                )

        member_token = proxy_token(runtime_endpoints.admin_mcp_url, member_bearer, identity)
        async with mcp_client(runtime_endpoints.admin_mcp_url, member_token) as member:
            assert not ADMINISTRATOR_TOOLS & {tool.name for tool in await member.list_tools()}
            denied = await member.call_tool(tool_name, arguments, raise_on_error=False)
            assert denied.is_error is True
            expected_error = (
                f"Unknown tool: '{tool_name}'"
                if runtime_endpoints.admin_mcp_url != runtime_endpoints.mcp_url
                else f"Authorization failed for tool '{tool_name}': not found or not authorized"
            )
            assert denied.content[0].text == expected_error
