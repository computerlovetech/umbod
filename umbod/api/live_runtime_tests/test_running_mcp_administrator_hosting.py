import os
import ssl
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator

from conftest import RuntimeEndpoints
from test_running_personal_mcp_execution import mcp_client, proxy_token

CONNECTOR = {"connector_kind": "native", "connector_id": "test"}
ADMINISTRATOR_REQUESTS = {
    "admin_discover": {"operation": "list_connectors"},
    "admin_inspect": {"operation": "read_connector_configuration", "connector": CONNECTOR},
    "admin_apply": {
        "operation": "update_connector_configuration",
        "connector": CONNECTOR,
        "desired_state": {},
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", sorted(ADMINISTRATOR_REQUESTS))
async def test_verified_administrator_tools_remain_authorized_only_on_administrator_endpoint(
    runtime_endpoints: RuntimeEndpoints, tool_name: str,
) -> None:
    member_bearer = os.environ.get("UMBOD_TEST_MEMBER_BEARER_TOKEN")
    if not member_bearer:
        pytest.skip("Requires the verified-user runtime stage")
    request = ADMINISTRATOR_REQUESTS[tool_name]
    arguments: dict[str, Any] = {"request": request}
    administrator_tools = set(ADMINISTRATOR_REQUESTS)
    context = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(
        base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=context, timeout=30,
    ) as identity:
        administrator_token = proxy_token(
            runtime_endpoints.admin_mcp_url, runtime_endpoints.bearer_token, identity,
        )
        async with mcp_client(runtime_endpoints.admin_mcp_url, administrator_token) as administrator:
            descriptors = {tool.name: tool for tool in await administrator.list_tools()}
            if runtime_endpoints.admin_mcp_url != runtime_endpoints.mcp_url:
                assert set(descriptors) == administrator_tools
            else:
                assert administrator_tools <= set(descriptors)
            result = await administrator.call_tool(tool_name, arguments)
            assert result.is_error is False
            output_schema = descriptors[tool_name].output_schema
            assert output_schema is not None
            Draft202012Validator(output_schema).validate(result.structured_content)
            operation_result = result.structured_content["result"]
            assert operation_result["operation"] == request["operation"]
            payload = operation_result["result"]
            if tool_name == "admin_discover":
                assert CONNECTOR in [entry["connector"] for entry in payload]
            else:
                assert payload["connector"] == CONNECTOR
            assert result.meta["computerlove.tech/umbod"]["guidance"]["outcome"] == "success"

        if runtime_endpoints.admin_mcp_url != runtime_endpoints.mcp_url:
            public_token = proxy_token(
                runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, identity,
            )
            async with mcp_client(runtime_endpoints.mcp_url, public_token) as public:
                assert not administrator_tools & {tool.name for tool in await public.list_tools()}
                denied = await public.call_tool(tool_name, arguments, raise_on_error=False)
                assert denied.is_error is True
                assert denied.content[0].text == (
                    f"Authorization failed for tool '{tool_name}': not found or not authorized"
                )

        member_token = proxy_token(runtime_endpoints.admin_mcp_url, member_bearer, identity)
        async with mcp_client(runtime_endpoints.admin_mcp_url, member_token) as member:
            assert not administrator_tools & {tool.name for tool in await member.list_tools()}
            denied = await member.call_tool(tool_name, arguments, raise_on_error=False)
            assert denied.is_error is True
            expected_error = (
                f"Unknown tool: '{tool_name}'"
                if runtime_endpoints.admin_mcp_url != runtime_endpoints.mcp_url
                else f"Authorization failed for tool '{tool_name}': not found or not authorized"
            )
            assert denied.content[0].text == expected_error
