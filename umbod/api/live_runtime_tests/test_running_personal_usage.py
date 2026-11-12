import asyncio
import os
import ssl
import time

import httpx
import pytest
from mcp.shared.exceptions import MCPError

from conftest import RuntimeEndpoints
from test_running_personal_mcp_execution import mcp_client, proxy_token
from umbod.rest.personal_usage.models import PersonalUsageResponse


pytestmark = pytest.mark.skipif(
    'UMBOD_TEST_MEMBER_BEARER_TOKEN' not in os.environ,
    reason='Requires the verified-user runtime stage',
)


def read_usage(client: httpx.Client, base_url: str, token: str) -> PersonalUsageResponse:
    response = client.get(base_url + '/api/me/usage', headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    return PersonalUsageResponse.model_validate(response.json())


async def exercise_usage(url: str, token: str) -> None:
    async with mcp_client(url, token) as client:
        await client.list_tools()
        await client.list_resources()
        await client.list_resource_templates()
        await client.list_prompts()
        result = await client.call_tool('filesystem_browse', {'operation': 'home'})
        assert result.is_error is False
        resources = await client.read_resource('umbod://setup/agent-instructions')
        assert len(resources) == 1
        with pytest.raises(MCPError):
            await client.get_prompt('personal_usage_missing_prompt', {})


def test_running_usage_crosses_mcp_and_rest_processes_without_crossing_users(runtime_endpoints: RuntimeEndpoints) -> None:
    member_token = os.environ['UMBOD_TEST_MEMBER_BEARER_TOKEN']
    other_token = runtime_endpoints.bearer_token
    second_api = os.environ['UMBOD_TEST_API_B_BASE_URL']
    tls = ssl.create_default_context(cafile=os.environ['UMBOD_TEST_PERSONAL_CA'])
    with httpx.Client(timeout=30) as http, httpx.Client(
        base_url=os.environ['UMBOD_TEST_PERSONAL_URL'], verify=tls, timeout=30, follow_redirects=False,
    ) as identity:
        before = read_usage(http, runtime_endpoints.api_base_url, member_token)
        other_before = read_usage(http, runtime_endpoints.api_base_url, other_token)
        authenticated_token = proxy_token(runtime_endpoints.mcp_url, member_token, identity)
        asyncio.run(exercise_usage(runtime_endpoints.mcp_url, authenticated_token))
        deadline = time.monotonic() + 20
        observed = before
        while time.monotonic() < deadline:
            observed = read_usage(http, second_api, member_token)
            if (
                observed.totals.tool.success >= before.totals.tool.success + 1
                and observed.totals.resource.success >= before.totals.resource.success + 1
                and observed.totals.prompt.failure >= before.totals.prompt.failure + 1
            ):
                break
            time.sleep(0.2)
        assert observed.totals.tool.success == before.totals.tool.success + 1
        assert observed.totals.resource.success == before.totals.resource.success + 1
        assert observed.totals.prompt.failure == before.totals.prompt.failure + 1
        assert observed.totals.total == before.totals.total + 3
        assert read_usage(http, runtime_endpoints.api_base_url, member_token).totals == observed.totals
        assert read_usage(http, runtime_endpoints.api_base_url, other_token).totals == other_before.totals
        assert len(observed.daily) == 7
        assert 'personal_usage_missing_prompt' not in observed.model_dump_json()
        assert http.get(runtime_endpoints.api_base_url + '/api/me/usage').status_code == 401
        injected = http.get(
            runtime_endpoints.api_base_url + '/api/me/usage',
            params={'owner': 'another-user'}, headers={'Authorization': 'Bearer ' + member_token},
        )
        assert injected.status_code == 422
