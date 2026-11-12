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
    assert received["permissions"] == node["permissions"]
    assert received["visible_to"] == node["visible_to"]
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
        for group in eligible["recipients"]
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
    assert sharing_write_payload(await alice.call_tool("filesystem_share", arguments)) == {**arguments, "recursive": False, "changed": True}
    assert sharing_write_payload(await alice.call_tool("filesystem_share", arguments)) == {**arguments, "recursive": False, "changed": False}
    extended = await alice.call_tool("filesystem_share", {**arguments, "permissions": ["discover"]})
    assert sharing_write_payload(extended) == {**arguments, "permissions": ["discover", "read"], "recursive": False, "changed": True}
    assert sharing_write_payload(await alice.call_tool("filesystem_share", arguments)) == {
        **arguments, "permissions": ["discover", "read"], "recursive": False, "changed": False,
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
            eligible_path = node_path + "/access/recipients?query=admin&recipient_type=group"
            eligible = alice.get(eligible_path)
            assert eligible.status_code == 200, eligible.text
            assert set(eligible.json()) == {"recipients", "has_more"}
            assert eligible.json()["has_more"] is False
            assert all(set(group) == {"type", "group_id", "label"} for group in eligible.json()["recipients"])
            assert "admin" in {group["group_id"] for group in eligible.json()["recipients"]}
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
            group = {"recipient": {"type": "group", "group_id": "admin"}, "permissions": ["discover", "read"], "recursive": False}
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
            assert bob.get(node_path + "/content?delivery=stream").content == b"direct-node sharing runtime"
            async with mcp_client(runtime_endpoints.mcp_url, alice_token) as alice_mcp, mcp_client(
                os.environ["UMBOD_TEST_MCP_B_URL"], bob_token,
            ) as bob_mcp:
                sharing = {"can_share": True, "grants": [{
                    "recipient": {
                        "type": "group", "group_id": "admin",
                        "label": next(entry["label"] for entry in eligible.json()["recipients"] if entry["group_id"] == "admin"),
                    },
                    "permissions": ["discover", "read"], "recursive": False,
                }]}
                await assert_mcp_sharing_metadata(alice_mcp, file, sharing)
                await assert_mcp_sharing_metadata(bob_mcp, reader_node, {"can_share": False})
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
                await assert_mcp_sharing_metadata(alice_mcp, checked_summary(alice.get(node_path), 200), {"can_share": True, "grants": []})
                denied_metadata = await bob_mcp.call_tool("get_filesystem_node", {"node_id": file["id"]}, raise_on_error=False)
                assert denied_metadata.is_error
                assert "filesystem_permission_denied" in denied_metadata.content[0].text
            assert bob.get(node_path).status_code == 403
            assert bob.get(node_path + "/content").status_code == 403
            folder_access = folder_path + "/access?recipient_type=group"
            folder_policy = alice.get(folder_access)
            folder_shared = alice.put(folder_access, json={"grants": [group]}, headers={"If-Match": folder_policy.headers["etag"]})
            assert folder_shared.status_code == 200, folder_shared.text
            assert folder_shared.json()["grants"] == [{
                **group,
                "recipient": next(entry for entry in eligible.json()["recipients"] if entry["group_id"] == "admin"),
            }]
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


def create_sharing_directory(client: httpx.Client, parent_id: str, prefix: str) -> dict[str, Any]:
    return checked_summary(client.post(FILESYSTEM + "/nodes/" + parent_id + "/directories", json={
        "name": prefix + "-" + uuid4().hex,
        "metadata": {"content_type": {}, "attributes": {}},
    }), 201)


def replace_group_grants(
    client: httpx.Client, node_id: str, grants: list[dict[str, Any]],
) -> dict[str, Any]:
    path = FILESYSTEM + "/nodes/" + node_id + "/access?recipient_type=group"
    current = client.get(path)
    assert current.status_code == 200, current.text
    replaced = client.put(path, json={"grants": grants}, headers={"If-Match": current.headers["etag"]})
    assert replaced.status_code == 200, replaced.text
    return {key: value for key, value in replaced.json().items() if key != "visible_to"}


@pytest.mark.asyncio
async def test_signed_recursive_directory_sharing_tracks_descendants_moves_and_live_revocation(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    if jwt.get_unverified_header(runtime_endpoints.bearer_token).get("alg") != "RS256":
        pytest.skip("Requires the runner's signed personal-runtime phase")
    bob_bearer = os.environ["UMBOD_TEST_BEARER_TOKEN_B"]
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30) as identity:
        alice_token = proxy_token(runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, identity)
        bob_token = proxy_token(os.environ["UMBOD_TEST_MCP_B_URL"], bob_bearer, identity)
    with httpx.Client(
        base_url=runtime_endpoints.api_base_url,
        headers={"Authorization": "Bearer " + runtime_endpoints.bearer_token}, timeout=30,
    ) as alice, httpx.Client(
        base_url=os.environ["UMBOD_TEST_API_B_BASE_URL"],
        headers={"Authorization": "Bearer " + bob_bearer}, timeout=30,
    ) as bob, httpx.Client(
        base_url=runtime_endpoints.api_base_url,
        headers={"Authorization": "Bearer " + bob_bearer}, timeout=30,
    ) as bob_other_worker:
        assert alice.post("/api/admin/groups", json={"group_id": "admin"}).status_code == 204
        assert bob.get("/api/admin/groups").status_code == 200
        root_policy = "/api/admin/filesystem/root-access"
        previous = alice.get(root_policy).json()
        configured = alice.put(root_policy, json={
            "expected_revision": previous["revision"],
            "groups": [{"group_id": "admin", "permissions": ["discover", "write"]}],
        })
        assert configured.status_code == 200, configured.text
        files: list[dict[str, Any]] = []
        shared_directories: list[str] = []
        try:
            root = checked_root_browse(alice.get(FILESYSTEM + "/browse"))
            source = create_sharing_directory(alice, root["id"], "inheritance-source")
            shared = create_sharing_directory(alice, root["id"], "inheritance-shared")
            destination = create_sharing_directory(alice, root["id"], "inheritance-destination")
            nested = create_sharing_directory(alice, shared["id"], "nested")
            existing = upload_private_file(alice, nested["id"])
            files.append(existing)
            direct = upload_private_file(alice, nested["id"])
            files.append(direct)
            moving = upload_private_file(alice, source["id"])
            files.append(moving)
            group = {"recipient": {"type": "group", "group_id": "admin"}, "permissions": ["discover", "read"]}
            recipients = alice.get(FILESYSTEM + "/nodes/" + direct["id"] + "/access/recipients?recipient_type=group&query=admin")
            assert recipients.status_code == 200, recipients.text
            recipient = next(entry for entry in recipients.json()["recipients"] if entry["group_id"] == "admin")
            direct_policy = replace_group_grants(alice, direct["id"], [group])
            assert direct_policy["grants"] == [{**group, "recipient": recipient, "recursive": False}]
            assert bob.get(FILESYSTEM + "/nodes/" + direct["id"] + "/content?delivery=stream").status_code == 200
            for node in (source, shared, nested, destination, existing, moving):
                assert bob.get(FILESYSTEM + "/nodes/" + node["id"]).status_code == 403
            async with mcp_client(runtime_endpoints.mcp_url, alice_token) as alice_mcp, mcp_client(
                os.environ["UMBOD_TEST_MCP_B_URL"], bob_token,
            ) as bob_mcp:
                await wait_for_filesystem_tools(alice_mcp, {"filesystem_share"})
                await wait_for_filesystem_tools(bob_mcp, {"get_filesystem_node", "filesystem_browse"})
                command = {"node_id": shared["id"], "group_id": "admin", "permissions": ["discover"]}
                shared_directories.append(shared["id"])
                assert sharing_write_payload(await alice_mcp.call_tool("filesystem_share", command)) == {
                    **command, "recursive": True, "changed": True,
                }
                extended = {**command, "permissions": ["read"], "recursive": False}
                assert sharing_write_payload(await alice_mcp.call_tool("filesystem_share", extended)) == {
                    **extended, "permissions": ["discover", "read"], "recursive": True, "changed": True,
                }
                assert sharing_write_payload(await alice_mcp.call_tool("filesystem_share", extended)) == {
                    **extended, "permissions": ["discover", "read"], "recursive": True, "changed": False,
                }
                parent_path = FILESYSTEM + "/nodes/" + shared["id"]
                parent_policy = alice.get(parent_path + "/access?recipient_type=group")
                assert parent_policy.status_code == 200, parent_policy.text
                parent_grants = [{"recipient": recipient, "permissions": ["discover", "read"], "recursive": True}]
                assert parent_policy.json()["grants"] == parent_grants
                await assert_mcp_sharing_metadata(
                    alice_mcp, checked_summary(alice.get(parent_path), 200),
                    {"can_share": True, "grants": parent_grants},
                )
                await assert_mcp_sharing_metadata(
                    bob_mcp, checked_summary(bob.get(parent_path), 200), {"can_share": False},
                )
                later = upload_private_file(alice, nested["id"])
                files.append(later)
                for node in (existing, direct, later):
                    path = FILESYSTEM + "/nodes/" + node["id"]
                    for reader in (bob, bob_other_worker):
                        content = reader.get(path + "/content?delivery=stream")
                        assert content.status_code == 200, content.text
                        assert content.content == b"direct-node sharing runtime"
                        view = checked_summary(reader.get(path), 200)
                        assert view["permissions"] == {
                            "can_discover": True, "can_read": True, "can_write": False,
                            "can_delete": False, "can_share": False,
                        }
                    await assert_mcp_sharing_metadata(bob_mcp, view, {"can_share": False})
                for node in (nested, existing, later):
                    access = alice.get(FILESYSTEM + "/nodes/" + node["id"] + "/access?recipient_type=group")
                    assert access.status_code == 200, access.text
                    assert access.json()["grants"] == []
                    owner_node = checked_summary(alice.get(FILESYSTEM + "/nodes/" + node["id"]), 200)
                    await assert_mcp_sharing_metadata(alice_mcp, owner_node, {"can_share": True, "grants": []})
                assert alice.get(FILESYSTEM + "/nodes/" + direct["id"] + "/access?recipient_type=group").json() == direct_policy
                listing = bob.get(FILESYSTEM + "/browse", params={"node_id": nested["id"]})
                assert listing.status_code == 200, listing.text
                assert {entry["id"] for entry in listing.json()["entries"]} == {existing["id"], direct["id"], later["id"]}
                assert {item["node_id"] for item in listing.json()["capabilities"]} == {nested["id"], existing["id"], direct["id"], later["id"]}
                for capability in listing.json()["capabilities"]:
                    assert capability == {
                        "node_id": capability["node_id"], "rename": False, "move": False,
                        "edit_description": False, "delete": False, "share": False,
                        "upload": False, "create_directory": False,
                    }
                mcp_listing = tool_payload(await bob_mcp.call_tool("filesystem_browse", {
                    "operation": "ls", "target": {"type": "node", "node_id": nested["id"]},
                }))["result"]
                assert {
                    entry["id"]: entry["permissions"] for entry in mcp_listing["entries"]
                } == {
                    entry["id"]: entry["permissions"] for entry in listing.json()["entries"]
                }
                assert mcp_listing["node"]["permissions"] == listing.json()["node"]["permissions"]
                moving_path = FILESYSTEM + "/nodes/" + moving["id"]
                moved_in = checked_summary(alice.patch(moving_path, headers={"If-Match": f'"{moving["revision"]}"'}, json={
                    "parent_id": nested["id"],
                }), 200)
                assert bob.get(moving_path + "/content?delivery=stream").status_code == 200
                assert bob_other_worker.get(moving_path + "/content?delivery=stream").status_code == 200
                await assert_mcp_sharing_metadata(bob_mcp, checked_summary(bob.get(moving_path), 200), {"can_share": False})
                checked_summary(alice.patch(moving_path, headers={"If-Match": f'"{moved_in["revision"]}"'}, json={
                    "parent_id": destination["id"],
                }), 200)
                for reader in (bob, bob_other_worker):
                    assert reader.get(moving_path).status_code == 403
                    assert reader.get(moving_path + "/content").status_code == 403
                assert alice.get(moving_path + "/access?recipient_type=group").json()["grants"] == []
                assert replace_group_grants(alice, shared["id"], [])["grants"] == []
                shared_directories.remove(shared["id"])
                for node in (shared, nested, existing, later):
                    path = FILESYSTEM + "/nodes/" + node["id"]
                    for reader in (bob, bob_other_worker):
                        assert reader.get(path).status_code == 403
                        if node["kind"] == "file":
                            assert reader.get(path + "/content").status_code == 403
                    denied = await bob_mcp.call_tool("get_filesystem_node", {"node_id": node["id"]}, raise_on_error=False)
                    assert denied.is_error
                    assert "filesystem_permission_denied" in denied.content[0].text
                direct_path = FILESYSTEM + "/nodes/" + direct["id"]
                for reader in (bob, bob_other_worker):
                    direct_view = checked_summary(reader.get(direct_path), 200)
                    assert direct_view["permissions"]["can_read"] is True
                    assert reader.get(direct_path + "/content?delivery=stream").status_code == 200
                await assert_mcp_sharing_metadata(bob_mcp, direct_view, {"can_share": False})
                assert alice.get(direct_path + "/access?recipient_type=group").json() == direct_policy
        finally:
            try:
                for node_id in shared_directories:
                    replace_group_grants(alice, node_id, [])
                for node in files:
                    path = FILESYSTEM + "/nodes/" + node["id"]
                    current_file = checked_summary(alice.get(path), 200)
                    removed = alice.delete(path, headers={"If-Match": f'"{current_file["revision"]}"'})
                    assert removed.status_code == 204, removed.text
            finally:
                current = alice.get(root_policy).json()
                restored = alice.put(root_policy, json={
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
                assert bob.get(node_path + "/content?delivery=stream").content == b"direct-node sharing runtime"
                assert bob.get(FILESYSTEM + "/nodes/" + folder["id"]).status_code == 403
                group_command = {
                    "node_id": file["id"], "recipient": {"type": "group", "group_id": "admin"},
                    "permissions": ["discover", "read"],
                }
                assert sharing_write_payload(await alice_mcp.call_tool("filesystem_share", group_command)) == {**group_command, "recursive": False, "changed": True}
                mixed = tool_payload(await alice_mcp.call_tool("get_filesystem_node", {"node_id": file["id"]}))["sharing"]
                assert {grant["recipient"]["type"] for grant in mixed["grants"]} == {"group", "user"}
                stale = alice.put(group_access, json={"grants": []}, headers={"If-Match": initial_groups.headers["etag"]})
                assert stale.status_code == 412
                current_groups = alice.get(group_access)
                assert {grant["recipient"]["type"] for grant in current_groups.json()["grants"]} == {"group"}
                replaced = alice.put(group_access, json={"grants": []}, headers={"If-Match": current_groups.headers["etag"]})
                assert replaced.status_code == 200, replaced.text
                assert bob.get(node_path + "/content?delivery=stream").status_code == 200
                assert checked_summary(alice.get(node_path), 200)["revision"] == file["revision"]
                remaining = tool_payload(await alice_mcp.call_tool("get_filesystem_node", {"node_id": file["id"]}))["sharing"]
                assert remaining == {
                    "can_share": True, "grants": [{
                        "recipient": {"type": "user", "user_id": recipient["user_id"], "label": recipient["label"]},
                        "permissions": ["discover", "read"], "recursive": False,
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
