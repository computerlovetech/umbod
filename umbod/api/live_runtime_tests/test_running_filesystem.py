import json
import os
import ssl
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastmcp.client.client import CallToolResult

from conftest import RuntimeEndpoints
from test_running_personal_mcp_execution import mcp_client, proxy_token


FILESYSTEM = "/api/me/filesystem"


def tool_payload(result: CallToolResult) -> dict[str, Any]:
    assert not result.is_error
    payload = result.structured_content
    if payload is None:
        payload = json.loads(result.content[0].text)
    assert isinstance(payload, dict)
    return payload


def checked_summary(response: httpx.Response, status: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert set(payload) == {
        "id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision",
    }
    return payload


@pytest.mark.asyncio
async def test_verified_filesystem_is_shared_across_transports_and_workers_but_children_are_private(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    issuer_bearer = runtime_endpoints.bearer_token
    second_bearer = os.environ["UMBOD_TEST_BEARER_TOKEN_B"]
    second_api = os.environ["UMBOD_TEST_API_B_BASE_URL"]
    second_mcp = os.environ["UMBOD_TEST_MCP_B_URL"]
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers={"Authorization": "Bearer " + issuer_bearer}, timeout=30) as alice, httpx.Client(base_url=second_api, headers={"Authorization": "Bearer " + second_bearer}, timeout=30) as bob, httpx.Client(base_url=second_api, headers={"Authorization": "Bearer " + issuer_bearer}, timeout=30) as alice_second, httpx.Client(base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30, follow_redirects=False) as identity:
        assert httpx.get(runtime_endpoints.api_base_url + FILESYSTEM + "/root", timeout=30).status_code == 401
        policy_url = "/api/admin/filesystem/root-access"
        assert alice.get(FILESYSTEM + "/root").status_code == 403
        inspected = alice.get(policy_url)
        assert inspected.status_code == 200
        assert inspected.headers["cache-control"] == "no-store"
        policy = inspected.json()
        assert policy["status"] in ("uninitialized", "ready")
        assert policy["groups"] == []
        assert policy["suggested_issuer"] == "https://identity.personal-runtime.kind.invalid/"
        assert policy["group_claim"] == "groups"
        group = {"issuer": policy["suggested_issuer"], "group_id": "admin", "permissions": ["discover", "write"]}
        configured = alice.put(policy_url, json={"expected_revision": policy["revision"], "groups": [group]})
        assert configured.status_code == 200, configured.text
        assert configured.headers["cache-control"] == "no-store"
        assert configured.json()["status"] == "ready"
        root = checked_summary(alice.get(FILESYSTEM + "/root"), 200)
        assert checked_summary(bob.get(FILESYSTEM + "/root"), 200) == root
        alice_token = proxy_token(second_mcp, issuer_bearer, identity)
        bob_token = proxy_token(runtime_endpoints.mcp_url, second_bearer, identity)
        metadata = {"content_type": "text/plain", "attributes": {"label": "discover-visible"}}
        name = "private-" + uuid4().hex
        alice_directory = checked_summary(alice.post(FILESYSTEM + "/nodes/" + root["id"] + "/directories", json={"name": name, "metadata": metadata}), 201)
        async with mcp_client(second_mcp, alice_token) as alice_mcp, mcp_client(runtime_endpoints.mcp_url, bob_token) as bob_mcp:
            assert tool_payload(await alice_mcp.call_tool("get_filesystem_root", {})) == root
            assert tool_payload(await alice_mcp.call_tool("get_filesystem_node", {"node_id": alice_directory["id"]})) == alice_directory
            denied = await bob_mcp.call_tool("get_filesystem_node", {"node_id": alice_directory["id"]}, raise_on_error=False)
            assert denied.is_error
            assert "filesystem_permission_denied" in denied.content[0].text
            bob_listing = tool_payload(await bob_mcp.call_tool("list_filesystem_children", {"parent_id": root["id"]}))
            assert alice_directory["id"] not in {node["id"] for node in bob_listing["nodes"]}
            assert not any(node["name"].startswith("local-test-private-") for node in bob_listing["nodes"])
            forbidden_name = "injected-" + uuid4().hex
            injection = await bob_mcp.call_tool("create_filesystem_file", {"parent_id": root["id"], "name": forbidden_name, "metadata": metadata, "owner": "kind-ci"}, raise_on_error=False)
            assert injection.is_error
            assert forbidden_name not in {node["name"] for node in tool_payload(await bob_mcp.call_tool("list_filesystem_children", {"parent_id": root["id"]}))["nodes"]}
            rest_injection = bob.post(FILESYSTEM + "/nodes/" + root["id"] + "/files", json={"name": forbidden_name, "metadata": metadata, "owner": "kind-ci"})
            assert rest_injection.status_code == 422
            bob_file = tool_payload(await bob_mcp.call_tool("create_filesystem_file", {"parent_id": root["id"], "name": "bob-" + uuid4().hex, "metadata": metadata}))
            assert checked_summary(bob.get(FILESYSTEM + "/nodes/" + bob_file["id"]), 200) == bob_file
            forbidden = alice.get(FILESYSTEM + "/nodes/" + bob_file["id"])
            assert forbidden.status_code == 403
            assert forbidden.json()["detail"]["code"] == "filesystem_permission_denied"
            alice_file = tool_payload(await alice_mcp.call_tool("create_filesystem_file", {"parent_id": alice_directory["id"], "name": "draft", "metadata": metadata}))
            assert checked_summary(alice_second.get(FILESYSTEM + "/nodes/" + alice_file["id"]), 200) == alice_file
            child_response = alice.get(FILESYSTEM + "/nodes/" + alice_directory["id"] + "/children")
            assert child_response.status_code == 200
            assert child_response.json() == {"nodes": [alice_file]}
            assert child_response.headers["cache-control"] == "no-store"
            hidden_parent = await bob_mcp.call_tool("list_filesystem_children", {"parent_id": alice_directory["id"]}, raise_on_error=False)
            assert hidden_parent.is_error
            assert "filesystem_permission_denied" in hidden_parent.content[0].text
            missing = bob.get(FILESYSTEM + "/nodes/" + str(uuid4()))
            assert missing.status_code == forbidden.status_code
            assert missing.json() == forbidden.json()
            current_policy = alice.get(policy_url).json()
            revoked = alice.put(policy_url, json={"expected_revision": current_policy["revision"], "groups": []})
            assert revoked.status_code == 200, revoked.text
            assert revoked.json()["groups"] == []
            assert alice.get(FILESYSTEM + "/root").status_code == 403
            assert bob.get(FILESYSTEM + "/root").status_code == 403
            revoked_root = await bob_mcp.call_tool("get_filesystem_root", {}, raise_on_error=False)
            assert revoked_root.is_error
            assert "filesystem_permission_denied" in revoked_root.content[0].text
            assert checked_summary(alice_second.get(FILESYSTEM + "/nodes/" + alice_file["id"]), 200) == alice_file
            assert tool_payload(await bob_mcp.call_tool("get_filesystem_node", {"node_id": bob_file["id"]})) == bob_file
            stale = alice.put(policy_url, json={"expected_revision": current_policy["revision"], "groups": [group]})
            assert stale.status_code == 409
            assert stale.json()["detail"]["code"] == "filesystem_policy_stale"
            assert alice.get(FILESYSTEM + "/root").status_code == 403


@pytest.mark.parametrize("method,suffix,body", [
    ("GET", "/nodes?scope=owned", {}),
    ("GET", "/nodes?scope=shared", {}),
    ("GET", "/nodes/{id}/breadcrumbs", {}),
    ("GET", "/nodes/{id}/content", {}),
    ("PUT", "/nodes/{id}/content", {}),
    ("PATCH", "/nodes/{id}", {"name": "renamed"}),
    ("DELETE", "/nodes/{id}", {}),
    ("GET", "/nodes/{id}/access", {}),
    ("PUT", "/nodes/{id}/access", {"grants": []}),
])
def test_planned_filesystem_endpoints_return_explicit_unimplemented_responses(
    runtime_endpoints: RuntimeEndpoints, method: str, suffix: str, body: dict[str, Any],
) -> None:
    path = FILESYSTEM + suffix.format(id=uuid4())
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers={
        "Authorization": "Bearer " + runtime_endpoints.bearer_token,
        "If-Match": '"1"',
    }, timeout=30) as client:
        before = client.get("/api/admin/filesystem/root-access")
        assert before.status_code == 200
        response = client.request(method, path, json=body)
        assert response.status_code == 501, response.text
        assert response.json()["detail"]["code"] == "filesystem_not_implemented"
        assert response.headers["cache-control"] == "no-store"
        after = client.get("/api/admin/filesystem/root-access")
        assert after.status_code == 200
        assert after.json() == before.json()
    unauthenticated = httpx.request(
        method, runtime_endpoints.api_base_url + path, json=body, timeout=30,
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", [
    "/api/admin/users", "/api/admin/openapi.json", "/api/me/catalogue",
    "/api/me/filesystem/root", "/api/me/openapi.json", "/api/future-protected-route",
])
def test_signed_rest_boundary_requires_authentication(
    runtime_endpoints: RuntimeEndpoints, path: str,
) -> None:
    response = httpx.get(runtime_endpoints.api_base_url + path, headers={
        "X-Umbod-Test-User": "Test User", "X-Authentication-Provenance": "local_simulation",
    }, timeout=30)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/system/health", "/api/system/health"])
def test_signed_rest_boundary_preserves_public_health(
    runtime_endpoints: RuntimeEndpoints, path: str,
) -> None:
    response = httpx.get(runtime_endpoints.api_base_url + path, timeout=30)
    assert response.status_code == 200


def test_planned_multipart_upload_does_not_create_an_empty_file(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers={
        "Authorization": "Bearer " + runtime_endpoints.bearer_token,
    }, timeout=30) as client:
        response = client.post(FILESYSTEM + "/nodes/" + str(uuid4()) + "/files", files={
            "file": ("notes.txt", b"Upload content must not create a placeholder.", "text/plain"),
        })
    assert response.status_code == 501, response.text
    assert response.json()["detail"]["code"] == "filesystem_not_implemented"
    assert response.headers["cache-control"] == "no-store"
