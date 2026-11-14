from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from conftest import RuntimeEndpoints
from test_running_filesystem import FILESYSTEM, FILESYSTEM_TOOLS, RETIRED_TOOLS, STRUCTURAL_ROOT, checked_namespace_browse, checked_summary


@pytest.mark.asyncio
async def test_local_rest_personal_namespace_works_while_mcp_requires_verified_identity(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as rest:
        assert rest.get("/api/me/profile").status_code == 200
        namespaces = rest.get(FILESYSTEM + "/namespaces")
        assert namespaces.status_code == 200
        personal = namespaces.json()["namespaces"][0]
        assert personal["kind"] == "personal"
        home = checked_namespace_browse(rest.get(FILESYSTEM + "/browse"))
        assert home["id"] == personal["root_node_id"]
        denied = rest.get(FILESYSTEM + "/browse", params={"node_id": STRUCTURAL_ROOT})
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == "filesystem_permission_denied"
        assert denied.headers["cache-control"] == "no-store"
        child = checked_summary(rest.post(FILESYSTEM + "/nodes/" + home["id"] + "/directories", json={
            "name": "local-test-private-" + uuid4().hex,
            "metadata": {"content_type": {}, "attributes": {}},
        }), 201)
        assert rest.get(FILESYSTEM + "/nodes/" + child["id"]).json() == child
        assert child in rest.get(FILESYSTEM + "/nodes/" + home["id"] + "/children").json()["nodes"]
        assert rest.get("/api/admin/filesystem/root-access").status_code == 404
        headers = {"Authorization": "Bearer " + runtime_endpoints.bearer_token}
        client: Client[Any] = Client(StreamableHttpTransport(runtime_endpoints.mcp_url, headers=headers))
        async with client:
            assert not {tool.name for tool in await client.list_tools()} & (FILESYSTEM_TOOLS | RETIRED_TOOLS)
            denied_tool = await client.call_tool("filesystem_browse", {"operation": "namespaces"}, raise_on_error=False)
            assert denied_tool.is_error
            for retired in RETIRED_TOOLS:
                assert (await client.call_tool(retired, {}, raise_on_error=False)).is_error
