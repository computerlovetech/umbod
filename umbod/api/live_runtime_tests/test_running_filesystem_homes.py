import asyncio
import hashlib
import os
import ssl
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
from fastmcp import Client

from conftest import RuntimeEndpoints
from test_running_filesystem import (
    FILESYSTEM, checked_summary, node_identity, sharing_write_payload, tool_payload, wait_for_filesystem_tools,
)
from test_running_personal_mcp_execution import mcp_client, proxy_token


@dataclass
class HomeRuntime:
    api: httpx.Client
    other_api: httpx.Client
    client: Client[Any]
    second_client: Client[Any]
    other_client: Client[Any]


@pytest_asyncio.fixture
async def home_runtime(runtime_endpoints: RuntimeEndpoints) -> AsyncIterator[HomeRuntime]:
    if jwt.get_unverified_header(runtime_endpoints.bearer_token).get("alg") != "RS256":
        pytest.skip("Requires the runner's signed personal-runtime phase")
    second_mcp = os.environ["UMBOD_TEST_MCP_B_URL"]
    other_bearer = os.environ["UMBOD_TEST_BEARER_TOKEN_B"]
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(
        base_url=os.environ["UMBOD_TEST_API_B_BASE_URL"], timeout=30,
        headers={"Authorization": "Bearer " + runtime_endpoints.bearer_token},
    ) as api, httpx.Client(
        base_url=runtime_endpoints.api_base_url, timeout=30,
        headers={"Authorization": "Bearer " + other_bearer},
    ) as other_api, httpx.Client(
        base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30,
    ) as identity:
        policy_path = "/api/admin/filesystem/root-access"
        previous_response = api.get(policy_path)
        assert previous_response.status_code == 200
        previous = previous_response.json()
        disabled = api.put(policy_path, json={"expected_revision": previous["revision"], "groups": []})
        assert disabled.status_code == 200, disabled.text
        try:
            assert api.get(FILESYSTEM + "/browse").status_code == 403
            assert other_api.get(FILESYSTEM + "/browse").status_code == 403
            token = proxy_token(runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, identity)
            second_token = proxy_token(second_mcp, runtime_endpoints.bearer_token, identity)
            other_token = proxy_token(second_mcp, other_bearer, identity)
            async with mcp_client(runtime_endpoints.mcp_url, token) as client, mcp_client(
                second_mcp, second_token,
            ) as second_client, mcp_client(second_mcp, other_token) as other_client:
                await wait_for_filesystem_tools(client, {"filesystem_browse"})
                await wait_for_filesystem_tools(other_client, {"filesystem_browse"})
                yield HomeRuntime(api, other_api, client, second_client, other_client)
        finally:
            current = api.get(policy_path)
            assert current.status_code == 200
            restored = api.put(policy_path, json={
                "expected_revision": current.json()["revision"], "groups": previous["groups"],
            })
            assert restored.status_code == 200, restored.text


def restore_admin_root_access(api: httpx.Client) -> None:
    path = "/api/admin/filesystem/root-access"
    current = api.get(path)
    assert current.status_code == 200
    configured = api.put(path, json={
        "expected_revision": current.json()["revision"],
        "groups": [{"group_id": "admin", "permissions": ["discover", "write"]}],
    })
    assert configured.status_code == 200, configured.text


@pytest.mark.asyncio
async def test_home_is_stable_private_and_independent_of_shared_root_access(home_runtime: HomeRuntime) -> None:
    runtime = home_runtime
    responses = await asyncio.gather(
        runtime.client.call_tool("filesystem_browse", {"operation": "home"}),
        runtime.second_client.call_tool("filesystem_browse", {"operation": "home"}),
    )
    homes = [tool_payload(response)["result"]["node"] for response in responses]
    home = homes[0]
    assert homes[1] == home
    assert home["permissions"] == {
        "can_discover": True, "can_read": True, "can_write": True, "can_delete": False, "can_share": True,
    }
    assert home["visible_to"]["type"] == "available"
    assert home["visible_to"]["owner"]["type"] == "user"
    assert home["visible_to"]["grants"] == []
    assert home["visible_to"]["group_members_expanded"] is False
    rest_home = checked_summary(runtime.api.post(FILESYSTEM + "/home"), 200)
    assert node_identity(rest_home) == node_identity(home)
    assert rest_home["permissions"] == home["permissions"]
    assert rest_home["visible_to"] == home["visible_to"]
    other = tool_payload(await runtime.other_client.call_tool("filesystem_browse", {"operation": "home"}))["result"]["node"]
    assert other["id"] != home["id"]
    assert other["visible_to"]["owner"] != home["visible_to"]["owner"]
    home_path = FILESYSTEM + "/nodes/" + home["id"]
    denied = runtime.other_api.get(home_path)
    missing = runtime.other_api.get(FILESYSTEM + "/nodes/" + str(uuid4()))
    assert denied.status_code == missing.status_code == 403
    assert denied.json() == missing.json()
    renamed = checked_summary(runtime.api.patch(
        home_path, headers={"If-Match": f'"{home["revision"]}"'}, json={"name": "My home-" + uuid4().hex},
    ), 200)
    repeated = tool_payload(await runtime.second_client.call_tool("filesystem_browse", {"operation": "home"}))
    assert repeated["result"]["node"]["id"] == home["id"]
    assert repeated["result"]["node"]["name"] == renamed["name"]
    assert repeated["result"]["breadcrumbs"]["complete"] is False
    restore_admin_root_access(runtime.api)
    root = runtime.api.get(FILESYSTEM + "/browse")
    assert root.status_code == 200, root.text
    visible_ids = {entry["id"] for entry in root.json()["entries"]}
    assert home["id"] in visible_ids
    assert other["id"] not in visible_ids
    other_root = runtime.other_api.get(FILESYSTEM + "/browse")
    assert other_root.status_code == 200, other_root.text
    other_visible_ids = {entry["id"] for entry in other_root.json()["entries"]}
    assert other["id"] in other_visible_ids
    assert home["id"] not in other_visible_ids


@pytest.mark.asyncio
async def test_upload_to_home_reports_current_permissions_and_direct_visibility(home_runtime: HomeRuntime) -> None:
    runtime = home_runtime
    home = checked_summary(runtime.api.post(FILESYSTEM + "/home"), 200)
    checked_summary(runtime.other_api.post(FILESYSTEM + "/home"), 200)
    await wait_for_filesystem_tools(runtime.client, {"filesystem_begin_upload", "filesystem_complete_upload"})
    data = b"Original strategy bytes\x00\xff\r\n"
    digest = hashlib.sha256(data).hexdigest()
    begun = tool_payload(await runtime.client.call_tool("filesystem_begin_upload", {
        "parent_id": home["id"], "name": "strategy-" + uuid4().hex + ".md", "size_bytes": len(data),
        "expected_sha256": digest, "metadata": {"content_type": "application/octet-stream", "attributes": {}},
    }))
    transfer = begun["transfer"]
    with httpx.Client(timeout=30, follow_redirects=False) as anonymous:
        transferred = anonymous.put(transfer["url"], headers=transfer["headers"], content=data)
        assert transferred.status_code == 204, transferred.text
    await wait_for_filesystem_tools(runtime.second_client, {"filesystem_complete_upload"})
    receipt = tool_payload(await runtime.second_client.call_tool("filesystem_complete_upload", {"upload_id": begun["upload_id"]}))
    file = receipt["node"]
    assert file["parent_id"] == home["id"]
    assert receipt["size_bytes"] == len(data)
    assert receipt["sha256"] == digest
    assert file["permissions"]["can_write"] is True
    assert file["visible_to"]["type"] == "available"
    assert file["visible_to"]["grants"] == []
    path = FILESYSTEM + "/nodes/" + file["id"]
    assert runtime.api.get(path + "/content").content == data
    restore_admin_root_access(runtime.api)
    assert runtime.other_api.get(path).status_code == 403
    await wait_for_filesystem_tools(runtime.client, {"filesystem_share"})
    shared = sharing_write_payload(await runtime.client.call_tool("filesystem_share", {
        "node_id": file["id"], "group_id": "admin", "permissions": ["discover", "read", "write"],
    }))
    assert shared["changed"] is True
    reader = checked_summary(runtime.other_api.get(path), 200)
    assert reader["permissions"]["can_write"] is True
    assert reader["permissions"]["can_share"] is False
    assert reader["visible_to"] == {"type": "restricted"}
    await wait_for_filesystem_tools(runtime.other_client, {"update_filesystem_node"})
    updated = tool_payload(await runtime.other_client.call_tool("update_filesystem_node", {
        "node_id": file["id"], "expected_revision": reader["revision"],
        "metadata": {"attributes": {"description": "Explicitly shared strategy"}},
    }))
    assert updated["visible_to"] == {"type": "restricted"}
    policy_path = path + "/access?recipient_type=group"
    policy = runtime.api.get(policy_path)
    assert policy.status_code == 200
    revoked = runtime.api.put(policy_path, headers={"If-Match": policy.headers["etag"]}, json={
        "grants": [{"recipient": {"type": "group", "group_id": "admin"}, "permissions": ["discover", "read"]}],
    })
    assert revoked.status_code == 200, revoked.text
    reader = checked_summary(runtime.other_api.get(path), 200)
    assert reader["permissions"]["can_write"] is False
    denied = await runtime.other_client.call_tool("update_filesystem_node", {
        "node_id": file["id"], "expected_revision": reader["revision"],
        "metadata": {"attributes": {"description": "Revoked writer"}},
    }, raise_on_error=False)
    assert denied.is_error
    assert "filesystem_permission_denied" in denied.content[0].text
    replayed = tool_payload(await runtime.client.call_tool("filesystem_complete_upload", {"upload_id": begun["upload_id"]}))
    assert replayed["sha256"] == digest
    assert replayed["node"]["id"] == file["id"]
    visibility = replayed["node"]["visible_to"]
    assert visibility["type"] == "available"
    assert visibility["group_members_expanded"] is False
    assert len(visibility["grants"]) == 1
    assert visibility["grants"][0]["principal"]["id"] == "admin"
    assert set(visibility["grants"][0]["permissions"]) == {"discover", "read"}
