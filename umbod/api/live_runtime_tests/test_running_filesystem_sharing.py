import os
import ssl
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest
from fastmcp import Client

from conftest import RuntimeEndpoints
from test_running_filesystem import (
    FILESYSTEM, check_access_metadata, checked_root_browse, checked_summary, node_identity,
    sharing_write_payload, tool_payload, wait_for_filesystem_tools,
)
from test_running_personal_mcp_execution import mcp_client, proxy_token
from upload_transfer_support import assert_transfer_succeeded, transfer_upload
from user_sharing_support import assert_mcp_user_target_sharing, assert_rest_recipient_scopes, observed_recipient


def upload_private_file(client: httpx.Client, parent_id: str) -> dict[str, Any]:
    content = b"direct-node sharing runtime"
    begun = client.post(FILESYSTEM + "/nodes/" + parent_id + "/uploads", json={
        "name": "sharing-" + uuid4().hex,
        "metadata": {"content_type": "text/plain", "attributes": {}},
        "size_bytes": len(content),
    })
    assert begun.status_code == 201, "Upload begin failed"
    upload = begun.json()
    assert_transfer_succeeded(transfer_upload(client, upload["transfer"], content))
    return checked_summary(client.post(upload["complete_url"]), 201)


async def assert_mcp_sharing_metadata(
    client: Client[Any], node: dict[str, Any], sharing: dict[str, Any],
) -> None:
    received = tool_payload(await client.call_tool("get_filesystem_node", {"node_id": node["id"]}))
    assert node_identity(received) == node_identity(node)
    assert received["sharing"] == sharing
    check_access_metadata(received)
    assert received["permissions"]["can_share"] == sharing["can_share"]
    if sharing["can_share"]:
        assert received["visible_to"]["type"] == "available"
        assert len(received["visible_to"]["grants"]) == len(sharing["grants"])
    else:
        assert received["visible_to"] == {"type": "restricted"}
    inspected = tool_payload(await client.call_tool("filesystem_browse", {
        "operation": "stat", "target": {"type": "node", "node_id": node["id"]},
    }))
    assert inspected["result"]["node"] == received


async def assert_mcp_additive_sharing(
    alice: Client[Any], bob: Client[Any], node_id: str, eligible: dict[str, Any],
) -> None:
    await wait_for_filesystem_tools(alice, {"filesystem_search_sharing_recipients", "filesystem_share"})
    await wait_for_filesystem_tools(bob, {"filesystem_search_sharing_recipients", "filesystem_share"})
    search = {"node_id": node_id, "query": "admin", "recipient_type": "group"}
    expected = sorted((
        {"type": "group", "group_id": group["group_id"], "label": group["label"]}
        for group in eligible["groups"]
        if "admin" in group["group_id"].casefold() or "admin" in group["label"].casefold()
    ), key=lambda recipient: (recipient["label"].casefold(), recipient["group_id"]))
    assert tool_payload(await alice.call_tool("filesystem_search_sharing_recipients", search)) == {
        "recipients": expected, "has_more": False,
    }
    arguments = {"node_id": node_id, "group_id": "admin", "permissions": ["read"]}
    unknown = await alice.call_tool("filesystem_share", {**arguments, "group_id": "unregistered-" + uuid4().hex}, raise_on_error=False)
    assert unknown.is_error
    assert unknown.content[0].text == "filesystem_invalid_sharing_policy: Invalid filesystem sharing policy. Select valid recipients and permissions, then retry."
    denied_groups = await bob.call_tool("filesystem_search_sharing_recipients", search, raise_on_error=False)
    missing_groups = await bob.call_tool("filesystem_search_sharing_recipients", {**search, "node_id": str(uuid4())}, raise_on_error=False)
    assert denied_groups.is_error and missing_groups.is_error
    assert denied_groups.content[0] == missing_groups.content[0]
    denied_share = await bob.call_tool("filesystem_share", arguments, raise_on_error=False)
    missing_share = await bob.call_tool("filesystem_share", {**arguments, "node_id": str(uuid4())}, raise_on_error=False)
    assert denied_share.is_error and missing_share.is_error
    assert denied_share.content[0] == missing_share.content[0]
    assert sharing_write_payload(await alice.call_tool("filesystem_share", arguments)) == {**arguments, "changed": True}
    assert sharing_write_payload(await alice.call_tool("filesystem_share", arguments)) == {**arguments, "changed": False}
    extended = await alice.call_tool("filesystem_share", {**arguments, "permissions": ["discover"]})
    assert sharing_write_payload(extended) == {**arguments, "permissions": ["discover", "read"], "changed": True}
    assert sharing_write_payload(await alice.call_tool("filesystem_share", arguments)) == {
        **arguments, "permissions": ["discover", "read"], "changed": False,
    }


@pytest.mark.asyncio
async def test_signed_direct_node_group_sharing_and_revocation(runtime_endpoints: RuntimeEndpoints) -> None:
    if jwt.get_unverified_header(runtime_endpoints.bearer_token).get("alg") != "RS256":
        pytest.skip("Requires the runner's signed personal-runtime phase")
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30, follow_redirects=False) as identity:
        alice_token = proxy_token(runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, identity)
        bob_token = proxy_token(os.environ["UMBOD_TEST_MCP_B_URL"], os.environ["UMBOD_TEST_BEARER_TOKEN_B"], identity)
    with httpx.Client(
        base_url=runtime_endpoints.api_base_url,
        headers={"Authorization": "Bearer " + runtime_endpoints.bearer_token}, timeout=30,
    ) as alice, httpx.Client(
        base_url=os.environ["UMBOD_TEST_API_B_BASE_URL"],
        headers={"Authorization": "Bearer " + os.environ["UMBOD_TEST_BEARER_TOKEN_B"]}, timeout=30,
    ) as bob:
        assert bob.get("/api/admin/groups").status_code == 200
        assert alice.post("/api/admin/groups", json={"group_id": "admin"}).status_code == 204
        root_policy_path = "/api/admin/filesystem/root-access"
        previous = alice.get(root_policy_path).json()
        configured = alice.put(root_policy_path, json={
            "expected_revision": previous["revision"],
            "groups": [{"group_id": "admin", "permissions": ["discover", "write"]}],
        })
        assert configured.status_code == 200, configured.text
        try:
            root = checked_root_browse(alice.get(FILESYSTEM + "/browse"))
            checked_summary(bob.post(FILESYSTEM + "/nodes/" + root["id"] + "/directories", json={
                "name": "bob-sharing-authority-" + uuid4().hex,
                "metadata": {"content_type": {}, "attributes": {}},
            }), 201)
            folder = checked_summary(alice.post(FILESYSTEM + "/nodes/" + root["id"] + "/directories", json={
                "name": "sharing-folder-" + uuid4().hex,
                "metadata": {"content_type": {}, "attributes": {}},
            }), 201)
            file = upload_private_file(alice, folder["id"])
            node_path = FILESYSTEM + "/nodes/" + file["id"]
            folder_path = FILESYSTEM + "/nodes/" + folder["id"]
            access_path = node_path + "/access?recipient_type=group"
            eligible_path = node_path + "/access/eligible-groups"
            eligible = alice.get(eligible_path)
            assert eligible.status_code == 200, eligible.text
            assert set(eligible.json()) == {"groups"}
            assert all(set(group) == {"group_id", "label", "description"} for group in eligible.json()["groups"])
            assert "admin" in {group["group_id"] for group in eligible.json()["groups"]}
            assert "etag" not in eligible.headers
            assert eligible.headers["cache-control"] == "no-store"
            assert bob.get(eligible_path).status_code == 403
            hidden = bob.get(access_path)
            absent = bob.get(FILESYSTEM + "/nodes/" + str(uuid4()) + "/access")
            assert hidden.status_code == absent.status_code == 403
            assert hidden.json() == absent.json()
            assert bob.get(node_path + "/content").status_code == 403
            initial = alice.get(access_path)
            assert initial.status_code == 200, initial.text
            assert initial.json()["grants"] == []
            assert set(initial.json()) == {"node_id", "revision", "grants", "blocked_recipients"}
            assert alice.put(access_path, json={"grants": []}).status_code == 428
            assert alice.put(access_path, json={"grants": []}, headers={"If-Match": '"1"'}).status_code == 422
            group = {"recipient": {"type": "group", "group_id": "admin"}, "permissions": ["discover", "read"]}
            async with mcp_client(runtime_endpoints.mcp_url, alice_token) as alice_mcp, mcp_client(
                os.environ["UMBOD_TEST_MCP_B_URL"], bob_token,
            ) as bob_mcp:
                await assert_mcp_additive_sharing(alice_mcp, bob_mcp, file["id"], eligible.json())
            shared = alice.get(access_path)
            assert shared.status_code == 200, shared.text
            assert shared.headers["etag"] != initial.headers["etag"]
            assert shared.headers["etag"] == '"' + shared.json()["revision"] + '"'
            assert shared.headers["cache-control"] == "no-store"
            reader_node = checked_summary(bob.get(node_path), 200)
            assert node_identity(reader_node) == node_identity(file)
            assert reader_node["permissions"]["can_read"] is True
            assert reader_node["permissions"]["can_write"] is False
            assert reader_node["visible_to"] == {"type": "restricted"}
            file = checked_summary(alice.get(node_path), 200)
            assert bob.get(node_path + "/content").content == b"direct-node sharing runtime"
            async with mcp_client(runtime_endpoints.mcp_url, alice_token) as alice_mcp, mcp_client(
                os.environ["UMBOD_TEST_MCP_B_URL"], bob_token,
            ) as bob_mcp:
                sharing = {"can_share": True, "grants": [{
                    "recipient": {
                        "type": "group", "group_id": "admin",
                        "label": next(entry["label"] for entry in eligible.json()["groups"] if entry["group_id"] == "admin"),
                    },
                    "permissions": ["discover", "read"],
                }]}
                await assert_mcp_sharing_metadata(alice_mcp, file, sharing)
                await assert_mcp_sharing_metadata(bob_mcp, file, {"can_share": False})
                denied_group_discovery = await bob_mcp.call_tool("filesystem_search_sharing_recipients", {
                    "node_id": file["id"], "query": "admin", "recipient_type": "group",
                }, raise_on_error=False)
                assert denied_group_discovery.is_error
                denied_delegation = await bob_mcp.call_tool("filesystem_share", {
                    "node_id": file["id"], "group_id": "admin", "permissions": ["share"],
                }, raise_on_error=False)
                assert denied_delegation.is_error
                assert "filesystem_permission_denied" in denied_delegation.content[0].text
                children = tool_payload(await alice_mcp.call_tool("list_filesystem_children", {"parent_id": folder["id"]}))
                assert children["nodes"] == [{**file, "sharing": sharing}]
                listed = tool_payload(await alice_mcp.call_tool("filesystem_browse", {
                    "operation": "ls", "target": {"type": "node", "node_id": folder["id"]},
                }))
                assert listed["result"]["entries"] == children["nodes"]
            assert bob.get(folder_path).status_code == 403
            assert bob.get(access_path).status_code == 403
            assert bob.get(eligible_path).status_code == 403
            assert alice.get(eligible_path).json() == eligible.json()
            denied = bob.put(access_path, json={"grants": []}, headers={"If-Match": initial.headers["etag"]})
            assert denied.status_code == 403
            stale = alice.put(access_path, json={"grants": []}, headers={"If-Match": initial.headers["etag"]})
            assert stale.status_code == 412
            revoked = alice.put(access_path, json={"grants": []}, headers={"If-Match": shared.headers["etag"]})
            assert revoked.status_code == 200, revoked.text
            assert revoked.json()["grants"] == []
            async with mcp_client(runtime_endpoints.mcp_url, alice_token) as alice_mcp, mcp_client(
                os.environ["UMBOD_TEST_MCP_B_URL"], bob_token,
            ) as bob_mcp:
                await assert_mcp_sharing_metadata(alice_mcp, file, {"can_share": True, "grants": []})
                denied_metadata = await bob_mcp.call_tool("get_filesystem_node", {"node_id": file["id"]}, raise_on_error=False)
                assert denied_metadata.is_error
                assert "filesystem_permission_denied" in denied_metadata.content[0].text
            assert bob.get(node_path).status_code == 403
            assert bob.get(node_path + "/content").status_code == 403
            folder_access = folder_path + "/access?recipient_type=group"
            folder_policy = alice.get(folder_access)
            folder_shared = alice.put(folder_access, json={"grants": [group]}, headers={"If-Match": folder_policy.headers["etag"]})
            assert folder_shared.status_code == 200, folder_shared.text
            assert bob.get(folder_path).status_code == 200
            assert bob.get(folder_path + "/children").json() == {"nodes": []}
            assert bob.get(node_path).status_code == 403
            assert bob.get(node_path + "/content").status_code == 403
        finally:
            current = alice.get(root_policy_path).json()
            restored = alice.put(root_policy_path, json={
                "expected_revision": current["revision"], "groups": previous["groups"],
            })
            assert restored.status_code == 200, restored.text


@pytest.mark.asyncio
async def test_signed_observed_user_and_group_targets_use_existing_sharing_tool(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    if jwt.get_unverified_header(runtime_endpoints.bearer_token).get("alg") != "RS256":
        pytest.skip("Requires the runner's signed personal-runtime phase")
    bob_bearer = os.environ["UMBOD_TEST_BEARER_TOKEN_B"]
    bob_claims = jwt.decode(bob_bearer, options={"verify_signature": False})
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(
        base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30,
    ) as identity:
        alice_token = proxy_token(runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, identity)
        bob_token = proxy_token(os.environ["UMBOD_TEST_MCP_B_URL"], bob_bearer, identity)
    with httpx.Client(
        base_url=runtime_endpoints.api_base_url,
        headers={"Authorization": "Bearer " + runtime_endpoints.bearer_token}, timeout=30,
    ) as alice, httpx.Client(
        base_url=os.environ["UMBOD_TEST_API_B_BASE_URL"],
        headers={"Authorization": "Bearer " + bob_bearer}, timeout=30,
    ) as bob:
        assert bob.post("/api/me/identity-observations").status_code == 204
        assert alice.post("/api/admin/groups", json={"group_id": "admin"}).status_code == 204
        root_policy = "/api/admin/filesystem/root-access"
        previous = alice.get(root_policy).json()
        configured = alice.put(root_policy, json={
            "expected_revision": previous["revision"],
            "groups": [{"group_id": "admin", "permissions": ["discover", "write"]}],
        })
        assert configured.status_code == 200, configured.text
        try:
            root = checked_root_browse(alice.get(FILESYSTEM + "/browse"))
            folder = checked_summary(alice.post(FILESYSTEM + "/nodes/" + root["id"] + "/directories", json={
                "name": "user-sharing-folder-" + uuid4().hex,
                "metadata": {"content_type": {}, "attributes": {}},
            }), 201)
            file = upload_private_file(alice, folder["id"])
            node_path = FILESYSTEM + "/nodes/" + file["id"]
            group_access = node_path + "/access?recipient_type=group"
            initial_groups = alice.get(group_access)
            assert initial_groups.status_code == 200
            assert bob.get(node_path + "/content").status_code == 403
            async with mcp_client(runtime_endpoints.mcp_url, alice_token) as alice_mcp, mcp_client(
                os.environ["UMBOD_TEST_MCP_B_URL"], bob_token,
            ) as bob_mcp:
                await wait_for_filesystem_tools(alice_mcp, {"filesystem_search_sharing_recipients", "filesystem_share"})
                await wait_for_filesystem_tools(bob_mcp, {"get_filesystem_node"})
                recipient = await observed_recipient(alice_mcp, file["id"], bob_claims["name"])
                await assert_mcp_user_target_sharing(alice_mcp, bob_mcp, file["id"], recipient)
                assert bob.get(node_path + "/content").content == b"direct-node sharing runtime"
                assert bob.get(FILESYSTEM + "/nodes/" + folder["id"]).status_code == 403
                group_command = {
                    "node_id": file["id"], "recipient": {"type": "group", "group_id": "admin"},
                    "permissions": ["discover", "read"],
                }
                assert sharing_write_payload(await alice_mcp.call_tool("filesystem_share", group_command)) == {**group_command, "changed": True}
                mixed = tool_payload(await alice_mcp.call_tool("get_filesystem_node", {"node_id": file["id"]}))["sharing"]
                assert {grant["recipient"]["type"] for grant in mixed["grants"]} == {"group", "user"}
                stale = alice.put(group_access, json={"grants": []}, headers={"If-Match": initial_groups.headers["etag"]})
                assert stale.status_code == 412
                current_groups = alice.get(group_access)
                assert {grant["recipient"]["type"] for grant in current_groups.json()["grants"]} == {"group"}
                replaced = alice.put(group_access, json={"grants": []}, headers={"If-Match": current_groups.headers["etag"]})
                assert replaced.status_code == 200, replaced.text
                assert bob.get(node_path + "/content").status_code == 200
                assert checked_summary(alice.get(node_path), 200)["revision"] == file["revision"]
                remaining = tool_payload(await alice_mcp.call_tool("get_filesystem_node", {"node_id": file["id"]}))["sharing"]
                assert remaining == {
                    "can_share": True, "grants": [{
                        "recipient": {"type": "user", "user_id": recipient["user_id"], "label": recipient["label"]},
                        "permissions": ["discover", "read"],
                    }],
                }
                assert_rest_recipient_scopes(alice, bob, node_path, recipient)
                assert checked_summary(alice.get(node_path), 200)["revision"] == file["revision"]
        finally:
            current = alice.get(root_policy).json()
            restored = alice.put(root_policy, json={
                "expected_revision": current["revision"], "groups": previous["groups"],
            })
            assert restored.status_code == 200, restored.text
