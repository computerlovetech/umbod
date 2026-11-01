import asyncio
import json
import os
import ssl
import time
from uuid import uuid4

import httpx
import jwt
import pytest

from conftest import RuntimeEndpoints
from test_running_filesystem import FILESYSTEM, checked_summary
from test_running_personal_mcp_execution import mcp_client, proxy_token


def test_development_identity_observation_is_skipped_without_mutation(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    if jwt.get_unverified_header(runtime_endpoints.bearer_token).get("alg") != "none":
        pytest.skip("Requires the runner's development-authentication phase")
    headers = {"Authorization": "Bearer " + runtime_endpoints.bearer_token}
    with httpx.Client(
        base_url=runtime_endpoints.api_base_url, headers=headers, timeout=30
    ) as client:
        before = client.get("/api/admin/identity-directory/users")
        assert before.status_code == 200, before.text
        groups = client.get("/api/admin/identity-directory/groups")
        assert groups.status_code == 200, groups.text
        assert client.post("/api/me/identity-observations").status_code == 204
        assert client.get("/api/admin/identity-directory/users").json() == before.json()
        assert (
            client.get("/api/admin/identity-directory/groups").json() == groups.json()
        )


def test_signed_identity_observation_and_admin_directory(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    if jwt.get_unverified_header(runtime_endpoints.bearer_token).get("alg") != "RS256":
        pytest.skip("Requires the runner's signed personal-runtime phase")
    headers = {"Authorization": "Bearer " + runtime_endpoints.bearer_token}
    with httpx.Client(
        base_url=runtime_endpoints.api_base_url, headers=headers, timeout=30
    ) as client:
        claims = jwt.decode(runtime_endpoints.bearer_token, options={"verify_signature": False})
        registered = client.get("/api/admin/groups")
        assert registered.status_code == 200, registered.text
        assert client.post("/api/me/identity-observations").status_code == 204
        deadline = time.monotonic() + 15
        while True:
            users = client.get("/api/admin/identity-directory/users")
            assert users.status_code == 200, users.text
            matching_users = [user for user in users.json()["users"] if user["subject"] == claims["sub"]]
            if matching_users or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        assert len(matching_users) == 1
        first = matching_users[0]
        assert first["issuer"] == users.json()["issuer"]
        assert first["user_id"]
        assert client.post("/api/me/identity-observations").status_code == 204
        repeated = client.get("/api/admin/identity-directory/users").json()["users"]
        matching_repeated = [user for user in repeated if user["subject"] == claims["sub"]]
        assert len(matching_repeated) == 1
        assert matching_repeated[0]["user_id"] == first["user_id"]
        groups = client.get("/api/admin/identity-directory/groups")
        assert groups.status_code == 200, groups.text
        assert set(groups.json()) == {"issuer", "claim", "groups", "has_more"}
        assert groups.json()["groups"]
        assert client.get("/api/admin/groups").json() == registered.json()
        assert (
            client.post(
                "/api/me/identity-observations", json={"groups": ["injected"]}
            ).status_code
            == 422
        )
        assert (
            client.get("/api/admin/identity-directory/groups?limit=101").status_code
            == 422
        )
    with httpx.Client(base_url=runtime_endpoints.api_base_url, timeout=30) as anonymous:
        assert anonymous.post("/api/me/identity-observations").status_code == 401
        assert anonymous.get("/api/admin/identity-directory/users").status_code == 401


@pytest.mark.asyncio
async def test_signed_rest_observation_is_searchable_through_mcp(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    if jwt.get_unverified_header(runtime_endpoints.bearer_token).get("alg") != "RS256":
        pytest.skip("Requires the runner's signed personal-runtime phase")
    headers = {"Authorization": "Bearer " + runtime_endpoints.bearer_token}
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(
        base_url=runtime_endpoints.api_base_url, headers=headers, timeout=30,
    ) as api, httpx.Client(
        base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30,
    ) as identity:
        assert api.post("/api/me/identity-observations").status_code == 204
        claims = jwt.decode(runtime_endpoints.bearer_token, options={"verify_signature": False})
        deadline = time.monotonic() + 15
        while True:
            observed = api.get("/api/admin/identity-directory/users", params={"query": claims["name"]})
            assert observed.status_code == 200
            matching_users = [user for user in observed.json()["users"] if user["subject"] == claims["sub"]]
            if matching_users or time.monotonic() >= deadline:
                break
            await asyncio.sleep(0.1)
        assert matching_users, "Signed identity observation did not become searchable before the deadline"
        expected = matching_users[0]
        policy_path = "/api/admin/filesystem/root-access"
        assert api.post("/api/admin/groups", json={"group_id": "admin"}).status_code == 204
        previous = api.get(policy_path).json()
        configured = api.put(policy_path, json={
            "expected_revision": previous["revision"],
            "groups": [{"group_id": "admin", "permissions": ["discover", "write"]}],
        })
        assert configured.status_code == 200, configured.text
        try:
            root = checked_summary(api.get(FILESYSTEM + "/root"), 200)
            node = checked_summary(api.post(FILESYSTEM + "/nodes/" + root["id"] + "/directories", json={
                "name": "recipient-search-" + uuid4().hex,
                "metadata": {"content_type": {}, "attributes": {}},
            }), 201)
            token = proxy_token(runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, identity)
            async with mcp_client(runtime_endpoints.mcp_url, token) as client:
                names = {tool.name for tool in await client.list_tools()}
                assert "filesystem_search_sharing_recipients" in names
                assert names.isdisjoint({"search_users", "filesystem_list_sharing_groups"})
                arguments = {"node_id": node["id"], "query": claims["name"]}
                result = await client.call_tool("filesystem_search_sharing_recipients", arguments)
                assert not result.is_error
                assert json.loads(result.content[0].text) == result.structured_content
                assert {"type": "user", "user_id": expected["user_id"], "label": expected["name"]} in result.structured_content["recipients"]
                assert all(
                    set(recipient) == {"type", "user_id", "label"} if recipient["type"] == "user"
                    else set(recipient) == {"type", "group_id", "label"}
                    for recipient in result.structured_content["recipients"]
                )
                assert len(result.structured_content["recipients"]) <= 50
                invalid = await client.call_tool(
                    "filesystem_search_sharing_recipients", {**arguments, "limit": 1}, raise_on_error=False,
                )
                assert invalid.is_error
        finally:
            current = api.get(policy_path).json()
            restored = api.put(policy_path, json={
                "expected_revision": current["revision"], "groups": previous["groups"],
            })
            assert restored.status_code == 200, restored.text
