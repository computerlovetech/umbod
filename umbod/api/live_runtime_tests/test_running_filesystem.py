import asyncio
import base64
import json
import os
import ssl
import time
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.client import CallToolResult
from fastmcp.client.transports import StreamableHttpTransport
from mcp.shared.exceptions import MCPError
from mcp.types import BlobResourceContents, ResourceLink, TextResourceContents

from conftest import RuntimeEndpoints
from test_running_personal_mcp_execution import mcp_client, proxy_token
from upload_transfer_support import assert_transfer_succeeded, s3_runtime, transfer_upload


FILESYSTEM = "/api/me/filesystem"
FILESYSTEM_TOOLS = frozenset({
    "filesystem_browse", "get_filesystem_root", "get_filesystem_node", "list_filesystem_children",
    "create_filesystem_file", "create_filesystem_directory", "filesystem_upload",
    "filesystem_begin_upload", "filesystem_complete_upload",
    "filesystem_delete_file", "filesystem_search_sharing_recipients", "filesystem_share",
    "update_filesystem_node",
})


class FileDeletionApprovals:
    def __init__(self) -> None:
        self.approved: bool = False
        self.messages: list[str] = []
        self.count: int = 0

    async def __call__(self, *args: object) -> dict[str, bool]:
        assert isinstance(args[0], str)
        self.messages.append(args[0])
        self.count += 1
        return {"value": self.approved}


async def wait_for_filesystem_tools(
    client: Client[Any], required: set[str], excluded: frozenset[str] = frozenset(),
) -> set[str]:
    deadline = time.monotonic() + 15
    while True:
        names = {tool.name for tool in await client.list_tools()} & FILESYSTEM_TOOLS
        if required <= names and not names & excluded:
            return names
        assert time.monotonic() < deadline, f"Filesystem tools did not reconcile: {names}; required={required}; excluded={excluded}"
        await asyncio.sleep(0.1)


def tool_payload(result: CallToolResult) -> dict[str, Any]:
    assert not result.is_error
    payload = result.structured_content
    if payload is None:
        payload = json.loads(result.content[0].text)
    assert isinstance(payload, dict)
    return payload


def file_resource_uri(node_id: str) -> str:
    return "umbod://filesystem/files/" + node_id


def file_resource_link(result: CallToolResult, node_id: str) -> str:
    links = [item for item in result.content if isinstance(item, ResourceLink)]
    link = next(item for item in links if str(item.uri) == file_resource_uri(node_id))
    return str(link.uri)


def check_access_metadata(node: dict[str, Any]) -> None:
    assert set(node["permissions"]) == {"can_discover", "can_read", "can_write", "can_delete", "can_share"}
    assert all(isinstance(value, bool) for value in node["permissions"].values())
    assert node["permissions"]["can_discover"] is True
    visibility = node["visible_to"]
    assert visibility["type"] in {"available", "restricted", "unavailable"}
    if visibility["type"] == "available":
        assert visibility["scope"] == "direct_node_policy"
        assert visibility["group_members_expanded"] is False
        assert all(grant["node_id"] == node["id"] for grant in visibility["grants"])
        assert all(type(grant["recursive"]) is bool for grant in visibility["grants"])
        if node["kind"] == "file":
            assert all(grant["recursive"] is False for grant in visibility["grants"])


def node_identity(node: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in node.items() if key not in {"permissions", "visible_to", "sharing"}}


def sharing_write_payload(result: CallToolResult) -> dict[str, Any]:
    payload = tool_payload(result)
    visibility = payload["visible_to"]
    assert visibility["type"] == "available"
    assert visibility["scope"] == "direct_node_policy"
    assert visibility["group_members_expanded"] is False
    assert all(grant["node_id"] == payload["node_id"] for grant in visibility["grants"])
    assert all(type(grant["recursive"]) is bool for grant in visibility["grants"])
    assert type(payload["recursive"]) is bool
    return {key: value for key, value in payload.items() if key != "visible_to"}


def checked_summary(response: httpx.Response, status: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert set(payload) == {
        "id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision",
        "permissions", "visible_to",
    }
    check_access_metadata(payload)
    return payload


def checked_root_browse(response: httpx.Response) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert set(payload) == {"node", "entries", "breadcrumbs", "capabilities", "truncated"}
    node = payload["node"]
    assert set(node) == {
        "id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision",
        "permissions", "visible_to",
    }
    check_access_metadata(node)
    assert node["parent_id"] == {}
    assert node["kind"] == "directory"
    assert payload["breadcrumbs"] == {
        "items": [{"id": node["id"], "name": node["name"], "kind": "directory"}],
        "complete": True,
    }
    return node


def checked_breadcrumbs(
    response: httpx.Response, nodes: list[dict[str, Any]], complete: bool,
) -> None:
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [{field: node[field] for field in ("id", "name", "kind")} for node in nodes],
        "complete": complete,
    }


async def check_filesystem_descriptions(
    alice: httpx.Client, alice_second: httpx.Client, bob: httpx.Client,
    alice_mcp: Client[Any], parent_id: str,
) -> None:
    for kind in ("file", "directory"):
        created = tool_payload(await alice_mcp.call_tool("create_filesystem_" + kind, {
            "parent_id": parent_id,
            "name": "description-" + uuid4().hex,
            "metadata": {
                "content_type": "text/plain",
                "attributes": {"description": "Reference material. Read before planning.", "label": "retained"},
            },
        }))
        node_path = FILESYSTEM + "/nodes/" + created["id"]
        before = checked_summary(alice_second.get(node_path), 200)
        assert before["metadata"]["attributes"]["description"] == "Reference material. Read before planning."
        eligibility = alice.options(node_path)
        assert eligibility.status_code == 204, eligibility.text
        allowed = {method.strip() for method in eligibility.headers["allow"].split(",")}
        assert allowed == ({"GET", "PATCH", "DELETE", "OPTIONS"} if kind == "file" else {"GET", "PATCH", "OPTIONS"})
        assert bob.options(node_path).status_code == 403
        headers = {"If-Match": f'"{before["revision"]}"'}
        denied = bob.patch(node_path, headers=headers, json={"metadata": {"attributes": {"description": "not allowed"}}})
        missing = bob.patch(FILESYSTEM + "/nodes/" + str(uuid4()), headers=headers, json={"metadata": {"attributes": {"description": "not allowed"}}})
        assert denied.status_code == missing.status_code == 403
        assert denied.json() == missing.json()
        assert alice.patch(node_path, json={"metadata": {"attributes": {"description": "missing revision"}}}).status_code == 428
        description = "Release notes.\nRead before publishing 東京."
        updated_response = alice.patch(node_path, headers=headers, json={"metadata": {
            "content_type": "text/markdown", "attributes": {"description": description, "release": "ready"},
        }})
        updated = checked_summary(updated_response, 200)
        assert updated_response.headers["etag"] == f'"{updated["revision"]}"'
        assert updated["revision"] == before["revision"] + 1
        assert updated["metadata"] == {
            "content_type": "text/markdown",
            "attributes": {"description": description, "label": "retained", "release": "ready"},
        }
        assert checked_summary(alice_second.get(node_path), 200) == updated
        assert (updated["name"], updated["parent_id"]) == (before["name"], before["parent_id"])
        stale = alice_second.patch(node_path, headers=headers, json={"metadata": {"attributes": {"description": "stale overwrite"}}})
        assert stale.status_code == 412, stale.text
        listing = await alice_mcp.call_tool("filesystem_browse", {
            "operation": "ls", "target": {"type": "node", "node_id": parent_id},
        })
        listed = tool_payload(listing)["result"]["entries"]
        assert next(node for node in listed if node["id"] == created["id"])["metadata"]["attributes"]["description"] == description
        cleared = tool_payload(await alice_mcp.call_tool("update_filesystem_node", {
            "node_id": created["id"], "expected_revision": updated["revision"],
            "metadata": {"attributes": {"description": ""}},
        }))
        assert cleared["revision"] == updated["revision"] + 1
        assert cleared["metadata"]["attributes"] == {"label": "retained", "release": "ready"}
        after = checked_summary(alice_second.get(node_path), 200)
        assert after["metadata"] == cleared["metadata"]
        assert after["revision"] == cleared["revision"]


async def check_filesystem_node_updates(
    alice: httpx.Client, alice_second: httpx.Client, bob: httpx.Client,
    alice_mcp: Client[Any], parent_id: str,
) -> None:
    metadata = {"content_type": "text/plain", "attributes": {"team": "retained"}}
    source = tool_payload(await alice_mcp.call_tool("create_filesystem_directory", {
        "parent_id": parent_id, "name": "update-source-" + uuid4().hex, "metadata": metadata,
    }))
    destination = tool_payload(await alice_mcp.call_tool("create_filesystem_directory", {
        "parent_id": parent_id, "name": "update-destination-" + uuid4().hex, "metadata": metadata,
    }))
    for kind in ("file", "directory"):
        arguments = {"parent_id": source["id"], "name": "original-" + kind, "metadata": metadata}
        if kind == "file":
            created = tool_payload(await alice_mcp.call_tool("filesystem_upload", {
                **arguments, "content": {"encoding": "utf-8", "text": "Stable bytes after rename and move."},
            }))
        else:
            created = tool_payload(await alice_mcp.call_tool("create_filesystem_directory", arguments))
        path = FILESYSTEM + "/nodes/" + created["id"]
        access_path = path + "/access?recipient_type=group"
        access = alice.get(access_path)
        assert access.status_code == 200, access.text
        shared = alice.put(access_path, headers={"If-Match": access.headers["etag"]}, json={
            "grants": [{"recipient": {"type": "group", "group_id": "admin"}, "permissions": ["discover", "read", "write"]}],
        })
        assert shared.status_code == 200, shared.text
        access_before = shared.json()
        assert access_before["visible_to"]["type"] == "available"
        direct_rename = checked_summary(bob.patch(path, headers={"If-Match": f'"{created["revision"]}"'}, json={"name": "direct-rename-" + kind}), 200)
        assert direct_rename["parent_id"] == source["id"]
        denied_move = bob.patch(path, headers={"If-Match": f'"{direct_rename["revision"]}"'}, json={
            "parent_id": destination["id"], "metadata": {"attributes": {"team": "must not persist"}},
        })
        assert denied_move.status_code == 403, denied_move.text
        owner_view = checked_summary(alice_second.get(path), 200)
        assert node_identity(owner_view) == node_identity(direct_rename)
        assert direct_rename["permissions"]["can_write"] is True
        assert direct_rename["permissions"]["can_share"] is False
        assert direct_rename["visible_to"] == {"type": "restricted"}
        assert owner_view["visible_to"]["type"] == "available"
        updated_mcp = tool_payload(await alice_mcp.call_tool("update_filesystem_node", {
            "node_id": created["id"], "expected_revision": direct_rename["revision"],
            "name": "moved-" + kind, "parent_id": destination["id"],
            "metadata": {"attributes": {"description": "Read after moving"}},
        }))
        updated = checked_summary(alice_second.get(path), 200)
        assert updated["id"] == created["id"]
        assert updated["name"] == "moved-" + kind
        assert updated["parent_id"] == destination["id"]
        assert updated["revision"] == direct_rename["revision"] + 1
        assert updated_mcp["revision"] == updated["revision"]
        assert updated["metadata"]["attributes"] == {"team": "retained", "description": "Read after moving"}
        access_after = alice_second.get(access_path)
        assert access_after.status_code == 200, access_after.text
        assert {field: value for field, value in access_after.json().items() if field != "revision"} == {
            field: value for field, value in access_before.items() if field not in {"revision", "visible_to"}
        }
        reader_view = checked_summary(bob.get(path), 200)
        assert node_identity(reader_view) == node_identity(updated)
        assert reader_view["permissions"]["can_write"] is True
        assert reader_view["permissions"]["can_share"] is False
        assert reader_view["visible_to"] == {"type": "restricted"}
        assert created["id"] not in {item["id"] for item in alice.get(FILESYSTEM + "/nodes/" + source["id"] + "/children").json()["nodes"]}
        inspected = tool_payload(await alice_mcp.call_tool("filesystem_browse", {
            "operation": "stat", "target": {"type": "node", "node_id": created["id"]},
        }))["result"]
        assert inspected["node"]["name"] == updated["name"]
        assert inspected["breadcrumbs"]["items"][-2]["id"] == destination["id"]
        stale = alice_second.patch(path, headers={"If-Match": f'"{direct_rename["revision"]}"'}, json={"name": "stale"})
        assert stale.status_code == 412, stale.text
        occupied = tool_payload(await alice_mcp.call_tool("create_filesystem_directory", {
            "parent_id": source["id"], "name": "occupied-" + kind, "metadata": metadata,
        }))
        collision = alice.patch(path, headers={"If-Match": f'"{updated["revision"]}"'}, json={
            "parent_id": source["id"], "name": occupied["name"], "metadata": {"attributes": {"team": "must not persist"}},
        })
        assert collision.status_code == 409, collision.text
        assert collision.json()["detail"]["code"] == "filesystem_name_collision"
        assert checked_summary(alice_second.get(path), 200) == updated
        if kind == "file":
            assert alice_second.get(path + "/content").content == b"Stable bytes after rename and move."
            contents = await alice_mcp.read_resource(file_resource_uri(created["id"]))
            assert isinstance(contents[0], TextResourceContents)
            assert contents[0].text == "Stable bytes after rename and move."
        else:
            child = tool_payload(await alice_mcp.call_tool("create_filesystem_directory", {
                "parent_id": created["id"], "name": "child", "metadata": metadata,
            }))
            cycle = alice.patch(path, headers={"If-Match": f'"{updated["revision"]}"'}, json={"parent_id": child["id"], "name": "must-not-rename"})
            assert cycle.status_code == 409, cycle.text
            assert cycle.json()["detail"]["code"] == "filesystem_invalid_move"
            assert checked_summary(alice_second.get(path), 200) == updated
            assert checked_summary(alice_second.get(FILESYSTEM + "/nodes/" + child["id"]), 200) == {field: child[field] for field in updated}


async def check_mcp_file_deletion(
    alice: httpx.Client, alice_second: httpx.Client,
    alice_mcp: Client[Any], bob_mcp: Client[Any], parent_id: str,
    approvals: FileDeletionApprovals,
) -> None:
    parent_path = FILESYSTEM + "/nodes/" + parent_id
    children_before = alice.get(parent_path + "/children").json()["nodes"]
    data = b"delete through MCP"
    started = alice.post(parent_path + "/uploads", json={
        "name": "mcp-delete-" + uuid4().hex,
        "metadata": {"content_type": "text/plain", "attributes": {}},
        "size_bytes": len(data),
    })
    assert started.status_code == 201, "Upload begin failed"
    upload = started.json()
    assert_transfer_succeeded(transfer_upload(alice_second, upload["transfer"], data))
    node = checked_summary(alice_second.post(upload["complete_url"]), 201)
    node_path = FILESYSTEM + "/nodes/" + node["id"]
    await wait_for_filesystem_tools(alice_mcp, {"filesystem_delete_file"})
    await wait_for_filesystem_tools(bob_mcp, {"filesystem_delete_file"})
    discovered = await alice_mcp.call_tool("get_filesystem_node", {"node_id": node["id"]})
    uri = file_resource_link(discovered, node["id"])
    contents = await alice_mcp.read_resource(uri)
    assert len(contents) == 1
    assert isinstance(contents[0], TextResourceContents)
    assert contents[0].text == data.decode("utf-8")
    with pytest.raises(MCPError) as denied_read:
        await bob_mcp.read_resource(uri)
    with pytest.raises(MCPError) as missing_read:
        await bob_mcp.read_resource(file_resource_uri(str(uuid4())))
    assert denied_read.value.error.message == missing_read.value.error.message
    with pytest.raises(MCPError):
        await alice_mcp.read_resource(file_resource_uri(parent_id))
    arguments = {"node_id": node["id"], "expected_revision": node["revision"]}
    descriptor = next(tool for tool in await alice_mcp.list_tools() if tool.name == "filesystem_delete_file")
    assert descriptor.annotations is not None
    assert descriptor.annotations.destructiveHint is True
    assert descriptor.annotations.readOnlyHint is False
    denied = await bob_mcp.call_tool("filesystem_delete_file", arguments, raise_on_error=False)
    missing = await bob_mcp.call_tool("filesystem_delete_file", {
        "node_id": str(uuid4()), "expected_revision": node["revision"],
    }, raise_on_error=False)
    assert denied.is_error and missing.is_error
    assert denied.content[0].text == missing.content[0].text
    assert "filesystem_permission_denied" in denied.content[0].text
    stale = await alice_mcp.call_tool("filesystem_delete_file", {
        "node_id": node["id"], "expected_revision": node["revision"] + 1,
    }, raise_on_error=False)
    assert stale.is_error
    assert "filesystem_revision_conflict" in stale.content[0].text
    assert alice.get(node_path + "/content").content == data
    directory = await alice_mcp.call_tool("filesystem_delete_file", {
        "node_id": parent_id, "expected_revision": 1,
    }, raise_on_error=False)
    assert directory.is_error
    assert "filesystem_wrong_node_kind" in directory.content[0].text
    assert approvals.count == 0
    assert approvals.messages == []
    unapproved = await alice_mcp.call_tool("filesystem_delete_file", arguments, raise_on_error=False)
    assert unapproved.is_error
    assert "filesystem_delete_approval_denied" in unapproved.content[0].text
    assert approvals.count == 1
    for worker in (alice, alice_second):
        assert checked_summary(worker.get(node_path), 200) == node
        retained = worker.get(node_path + "/content")
        assert retained.status_code == 200
        assert retained.content == data
    retained_contents = await alice_mcp.read_resource(uri)
    assert len(retained_contents) == 1
    assert isinstance(retained_contents[0], TextResourceContents)
    assert retained_contents[0].text == data.decode("utf-8")
    approvals.approved = True
    assert tool_payload(await alice_mcp.call_tool("filesystem_delete_file", arguments)) == {
        "node_id": node["id"], "deleted": True,
    }
    assert alice.get(node_path).status_code == 403
    assert alice_second.get(node_path).status_code == 403
    assert alice.get(node_path + "/content").status_code == 403
    assert alice_second.post(upload["complete_url"]).status_code == 403
    with pytest.raises(MCPError) as deleted_read:
        await alice_mcp.read_resource(uri)
    assert deleted_read.value.error.message == missing_read.value.error.message
    assert alice.get(parent_path + "/children").json()["nodes"] == children_before
    repeated = await alice_mcp.call_tool("filesystem_delete_file", arguments, raise_on_error=False)
    assert repeated.is_error
    assert "filesystem_permission_denied" in repeated.content[0].text
    assert approvals.count == 2
    assert len(approvals.messages) == 2
    assert all(node["id"] in message for message in approvals.messages)


@pytest.mark.asyncio
async def test_cross_worker_discovery_distinguishes_root_creation_from_direct_file_read(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    second_mcp = os.environ["UMBOD_TEST_MCP_B_URL"]
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(
        base_url=runtime_endpoints.api_base_url,
        headers={"Authorization": "Bearer " + runtime_endpoints.bearer_token}, timeout=30,
    ) as alice, httpx.Client(
        base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30,
    ) as identity:
        token = proxy_token(second_mcp, os.environ["UMBOD_TEST_BEARER_TOKEN_B"], identity)
        policy_path = "/api/admin/filesystem/root-access"
        previous_response = alice.get(policy_path)
        assert previous_response.status_code == 200
        previous = previous_response.json()
        configured = alice.put(policy_path, json={
            "expected_revision": previous["revision"],
            "groups": [{"group_id": "admin", "permissions": ["discover", "write"]}],
        })
        assert configured.status_code == 200, configured.text
        access_path = ""
        try:
            root = checked_root_browse(alice.get(FILESYSTEM + "/browse"))
            async with mcp_client(second_mcp, token) as bob:
                root_tools = {
                    "filesystem_browse", "get_filesystem_root", "get_filesystem_node", "list_filesystem_children",
                    "create_filesystem_file", "create_filesystem_directory", "filesystem_upload",
                    "filesystem_begin_upload", "filesystem_complete_upload",
                    "update_filesystem_node",
                }
                assert await wait_for_filesystem_tools(bob, root_tools, FILESYSTEM_TOOLS - root_tools) == root_tools
                folder = checked_summary(alice.post(FILESYSTEM + "/nodes/" + root["id"] + "/directories", json={
                    "name": "discovery-" + uuid4().hex,
                    "metadata": {"content_type": {}, "attributes": {}},
                }), 201)
                begun = alice.post(FILESYSTEM + "/nodes/" + folder["id"] + "/uploads", json={
                    "name": "direct-read.txt", "size_bytes": 0,
                    "metadata": {"content_type": "text/plain", "attributes": {}},
                })
                assert begun.status_code == 201, "Upload begin failed"
                upload = begun.json()
                assert_transfer_succeeded(transfer_upload(alice, upload["transfer"], b""))
                file = checked_summary(alice.post(upload["complete_url"]), 201)
                access_path = FILESYSTEM + "/nodes/" + file["id"] + "/access?recipient_type=group"
                initial = alice.get(access_path)
                assert initial.status_code == 200
                shared = alice.put(access_path, headers={"If-Match": initial.headers["etag"]}, json={
                    "grants": [{"recipient": {"type": "group", "group_id": "admin"}, "permissions": ["discover", "read"]}],
                })
                assert shared.status_code == 200, shared.text
                current = alice.get(policy_path)
                assert current.status_code == 200
                revoked = alice.put(policy_path, json={"expected_revision": current.json()["revision"], "groups": []})
                assert revoked.status_code == 200, revoked.text
                read_tools = {"filesystem_browse", "get_filesystem_node"}
                assert await wait_for_filesystem_tools(bob, read_tools, FILESYSTEM_TOOLS - read_tools) == read_tools
                discovered = await bob.call_tool("get_filesystem_node", {"node_id": file["id"]})
                contents = await bob.read_resource(file_resource_link(discovered, file["id"]))
                assert len(contents) == 1
                assert isinstance(contents[0], TextResourceContents)
                assert contents[0].text == ""
                root_error = await bob.call_tool("get_filesystem_root", {}, raise_on_error=False)
                assert root_error.is_error
                assert root_error.content[0].text == "Authorization failed for tool 'get_filesystem_root': not found or not authorized"
                with pytest.raises(MCPError) as denied:
                    await bob.read_resource(file_resource_uri(folder["id"]))
                with pytest.raises(MCPError) as missing:
                    await bob.read_resource(file_resource_uri(str(uuid4())))
                assert denied.value.error.message == missing.value.error.message
        finally:
            if access_path:
                current_access = alice.get(access_path)
                assert current_access.status_code == 200
                cleared = alice.put(access_path, json={"grants": []}, headers={"If-Match": current_access.headers["etag"]})
                assert cleared.status_code == 200, cleared.text
            current = alice.get(policy_path)
            assert current.status_code == 200
            restored = alice.put(policy_path, json={"expected_revision": current.json()["revision"], "groups": previous["groups"]})
            assert restored.status_code == 200, restored.text


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
        assert httpx.get(runtime_endpoints.api_base_url + FILESYSTEM + "/browse", timeout=30).status_code == 401
        policy_url = "/api/admin/filesystem/root-access"
        assert alice.get(FILESYSTEM + "/browse").status_code == 403
        inspected = alice.get(policy_url)
        assert inspected.status_code == 200
        assert inspected.headers["cache-control"] == "no-store"
        policy = inspected.json()
        assert policy["status"] in ("uninitialized", "ready")
        assert policy["groups"] == []
        assert set(policy) == {"status", "revision", "groups", "blocked_group_ids"}
        assert policy["blocked_group_ids"] == []
        group = {"group_id": "admin", "permissions": ["discover", "write"]}
        configured = alice.put(policy_url, json={"expected_revision": policy["revision"], "groups": [group]})
        assert configured.status_code == 200, configured.text
        assert configured.headers["cache-control"] == "no-store"
        assert set(configured.json()) == {"status", "revision", "groups", "blocked_group_ids"}
        assert configured.json()["status"] == "ready"
        root = checked_root_browse(alice.get(FILESYSTEM + "/browse"))
        root_listing = alice_second.get(FILESYSTEM + "/browse")
        assert root_listing.status_code == 200, root_listing.text
        assert root_listing.headers["cache-control"] == "no-store"
        assert root_listing.json()["node"] == root
        root_actions = next(item for item in root_listing.json()["capabilities"] if item["node_id"] == root["id"])
        assert root_actions == {
            "node_id": root["id"], "rename": False, "move": False,
            "edit_description": True, "delete": False, "share": False,
            "upload": True, "create_directory": True,
        }
        assert checked_root_browse(bob.get(FILESYSTEM + "/browse")) == root
        checked_breadcrumbs(alice_second.get(FILESYSTEM + "/nodes/" + root["id"] + "/breadcrumbs"), [root], True)
        alice_token = proxy_token(second_mcp, issuer_bearer, identity)
        bob_token = proxy_token(runtime_endpoints.mcp_url, second_bearer, identity)
        metadata = {"content_type": "text/plain", "attributes": {"label": "discover-visible"}}
        name = "private-" + uuid4().hex
        alice_directory = checked_summary(alice.post(FILESYSTEM + "/nodes/" + root["id"] + "/directories", json={"name": name, "metadata": metadata}), 201)
        breadcrumb_path = FILESYSTEM + "/nodes/" + alice_directory["id"] + "/breadcrumbs"
        checked_breadcrumbs(alice_second.get(breadcrumb_path), [root, alice_directory], True)
        denied_breadcrumbs = bob.get(breadcrumb_path)
        missing_breadcrumbs = bob.get(FILESYSTEM + "/nodes/" + str(uuid4()) + "/breadcrumbs")
        assert denied_breadcrumbs.status_code == missing_breadcrumbs.status_code == 403
        assert denied_breadcrumbs.json() == missing_breadcrumbs.json()
        assert httpx.get(runtime_endpoints.api_base_url + breadcrumb_path, timeout=30).status_code == 401
        uploads_path = FILESYSTEM + "/nodes/" + alice_directory["id"] + "/uploads"
        uploaded_bytes = b"\x00\xff\x80runtime upload\r\n\x00"
        upload_request = {
            "name": "résumé-東京.bin",
            "metadata": {"content_type": "application/octet-stream", "attributes": {}},
            "size_bytes": len(uploaded_bytes),
        }
        allowed = alice.options(uploads_path)
        assert allowed.status_code == 405, allowed.text
        assert {method.strip() for method in allowed.headers["allow"].split(",")} == {"POST"}
        assert bob.options(uploads_path).status_code == 405
        denied_upload = bob.post(uploads_path, json=upload_request)
        assert denied_upload.status_code == 403
        assert denied_upload.json()["detail"]["code"] == "filesystem_permission_denied"
        begun = alice.post(uploads_path, json=upload_request)
        assert begun.status_code == 201, "Upload begin failed"
        assert begun.headers["cache-control"] == "no-store"
        upload = begun.json()
        assert upload["transfer"]["type"] == "single"
        assert upload["transfer"]["method"] == "PUT"
        assert upload["transfer"]["authorization"] == {"type": "none" if s3_runtime() else "same_origin"}
        session = alice_second.get(begun.headers["location"])
        assert session.status_code == 200, session.text
        assert session.json()["status"] == "pending"
        assert bob.get(begun.headers["location"]).status_code == 403
        if not s3_runtime():
            assert bob.put(upload["transfer"]["url"], content=uploaded_bytes).status_code == 403
        assert bob.post(upload["complete_url"]).status_code == 403
        assert alice_second.post(upload["complete_url"]).status_code == 409
        assert_transfer_succeeded(transfer_upload(alice_second, upload["transfer"], uploaded_bytes))
        assert alice.get(begun.headers["location"]).json()["status"] == ("pending" if s3_runtime() else "uploaded")
        assert alice.get(FILESYSTEM + "/nodes/" + alice_directory["id"] + "/children").json()["nodes"] == []
        completed = alice.post(upload["complete_url"])
        uploaded = checked_summary(completed, 201)
        directory_listing = alice_second.get(FILESYSTEM + "/browse", params={"node_id": alice_directory["id"]})
        assert directory_listing.status_code == 200, directory_listing.text
        listing = directory_listing.json()
        assert listing["node"] == alice_directory
        assert listing["entries"] == [uploaded]
        assert listing["truncated"] is False
        assert [item["id"] for item in listing["breadcrumbs"]["items"]] == [root["id"], alice_directory["id"]]
        assert next(item for item in listing["capabilities"] if item["node_id"] == uploaded["id"]) == {
            "node_id": uploaded["id"], "rename": True, "move": True,
            "edit_description": True, "delete": True, "share": True,
            "upload": False, "create_directory": False,
        }
        file_listing = alice_second.get(FILESYSTEM + "/browse", params={"node_id": uploaded["id"]})
        assert file_listing.status_code == 200, file_listing.text
        assert file_listing.json()["node"] == uploaded
        assert file_listing.json()["entries"] == []
        denied_listing = bob.get(FILESYSTEM + "/browse", params={"node_id": alice_directory["id"]})
        missing_listing = bob.get(FILESYSTEM + "/browse", params={"node_id": str(uuid4())})
        assert denied_listing.status_code == missing_listing.status_code == 403
        assert denied_listing.json() == missing_listing.json()
        assert completed.headers["location"] == FILESYSTEM + "/nodes/" + uploaded["id"]
        assert checked_summary(alice_second.post(upload["complete_url"]), 200) == uploaded
        checked_breadcrumbs(
            alice_second.get(FILESYSTEM + "/nodes/" + uploaded["id"] + "/breadcrumbs"),
            [root, alice_directory, uploaded], True,
        )
        assert alice_second.get(begun.headers["location"]).json()["status"] == "completed"
        assert transfer_upload(alice, upload["transfer"], uploaded_bytes).status_code == (412 if s3_runtime() else 409)
        downloaded = alice_second.get(FILESYSTEM + "/nodes/" + uploaded["id"] + "/content")
        assert downloaded.status_code == 200
        assert downloaded.content == uploaded_bytes
        assert downloaded.headers["cache-control"] == "no-store"
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.headers["content-disposition"].startswith("attachment;")
        private_download = bob.get(FILESYSTEM + "/nodes/" + uploaded["id"] + "/content")
        missing_download = bob.get(FILESYSTEM + "/nodes/" + str(uuid4()) + "/content")
        assert private_download.status_code == missing_download.status_code == 403
        assert private_download.json() == missing_download.json()
        assert private_download.json()["detail"]["code"] == "filesystem_permission_denied"
        private_upload = bob.post(uploads_path, json={
            "name": "forbidden.bin", "metadata": metadata, "size_bytes": 7,
        })
        assert private_upload.status_code == 403
        approvals = FileDeletionApprovals()
        async with Client(
            StreamableHttpTransport(second_mcp, headers={"Authorization": "Bearer " + alice_token}),
            elicitation_handler=approvals,
        ) as alice_mcp, mcp_client(runtime_endpoints.mcp_url, bob_token) as bob_mcp:
            await wait_for_filesystem_tools(alice_mcp, set(FILESYSTEM_TOOLS))
            await wait_for_filesystem_tools(bob_mcp, {
                "get_filesystem_root", "get_filesystem_node", "list_filesystem_children", "create_filesystem_file",
            })
            assert tool_payload(await alice_mcp.call_tool("get_filesystem_root", {})) == {
                **root, "sharing": {"can_share": False},
            }
            assert tool_payload(await alice_mcp.call_tool("get_filesystem_node", {"node_id": alice_directory["id"]})) == {
                **alice_directory, "sharing": {"can_share": True, "grants": []},
            }
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
            rest_injection = bob.post(
                FILESYSTEM + "/nodes/" + root["id"] + "/uploads",
                json={"name": forbidden_name, "metadata": metadata, "size_bytes": 0, "owner": "kind-ci"},
            )
            assert rest_injection.status_code == 422
            assert forbidden_name not in {
                node["name"] for node in bob.get(FILESYSTEM + "/nodes/" + root["id"] + "/children").json()["nodes"]
            }
            bob_created = await bob_mcp.call_tool("create_filesystem_file", {"parent_id": root["id"], "name": "bob-" + uuid4().hex, "metadata": metadata})
            bob_summary = tool_payload(bob_created)
            assert bob_summary["sharing"] == {"can_share": True, "grants": []}
            bob_file = {field: value for field, value in bob_summary.items() if field != "sharing"}
            bob_uri = file_resource_link(bob_created, bob_file["id"])
            assert checked_summary(bob.get(FILESYSTEM + "/nodes/" + bob_file["id"]), 200) == bob_file
            forbidden = alice.get(FILESYSTEM + "/nodes/" + bob_file["id"])
            assert forbidden.status_code == 403
            assert forbidden.json()["detail"]["code"] == "filesystem_permission_denied"
            alice_created = await alice_mcp.call_tool("create_filesystem_file", {"parent_id": alice_directory["id"], "name": "draft", "metadata": metadata})
            alice_summary = tool_payload(alice_created)
            assert alice_summary["sharing"] == {"can_share": True, "grants": []}
            alice_file = {field: value for field, value in alice_summary.items() if field != "sharing"}
            alice_uri = file_resource_link(alice_created, alice_file["id"])
            assert checked_summary(alice_second.get(FILESYSTEM + "/nodes/" + alice_file["id"]), 200) == alice_file
            child_response = alice.get(FILESYSTEM + "/nodes/" + alice_directory["id"] + "/children")
            assert child_response.status_code == 200
            assert {node["id"] for node in child_response.json()["nodes"]} == {alice_file["id"], uploaded["id"]}
            assert child_response.headers["cache-control"] == "no-store"
            browse_target = {"type": "path", "path": "/" + name}
            listing = await alice_mcp.call_tool("filesystem_browse", {
                "operation": "ls", "target": browse_target,
            })
            listed = tool_payload(listing)["result"]
            assert file_resource_link(listing, alice_file["id"]) == alice_uri
            assert file_resource_link(listing, uploaded["id"]) == file_resource_uri(uploaded["id"])
            assert listed["node"] == {**alice_directory, "sharing": {"can_share": True, "grants": []}}
            assert {node["id"] for node in listed["entries"]} == {alice_file["id"], uploaded["id"]}
            assert all(node["sharing"] == {"can_share": True, "grants": []} for node in listed["entries"])
            legacy_children = tool_payload(await alice_mcp.call_tool("list_filesystem_children", {"parent_id": alice_directory["id"]}))
            assert {node["id"]: node for node in legacy_children["nodes"]} == {
                node["id"]: node for node in listed["entries"]
            }
            assert listed["breadcrumbs"]["complete"] is True
            limited = tool_payload(await alice_mcp.call_tool("filesystem_browse", {
                "operation": "ls", "target": browse_target, "max_entries": 1,
            }))["result"]
            assert len(limited["entries"]) == 1
            assert limited["truncated"] is True
            inspected = tool_payload(await alice_mcp.call_tool("filesystem_browse", {
                "operation": "stat", "target": {"type": "path", "path": "/" + name + "/draft"},
            }))["result"]
            assert inspected["node"] == {**alice_file, "sharing": {"can_share": True, "grants": []}}
            tree = tool_payload(await alice_mcp.call_tool("filesystem_browse", {
                "operation": "tree", "target": browse_target, "depth": 2,
            }))["result"]
            assert {entry["node"]["id"] for entry in tree["entries"]} == {alice_file["id"], uploaded["id"]}
            assert tree["node"]["sharing"] == {"can_share": True, "grants": []}
            assert all(entry["node"]["sharing"] == {"can_share": True, "grants": []} for entry in tree["entries"])
            private_tree = await bob_mcp.call_tool("filesystem_browse", {
                "operation": "tree", "target": browse_target,
            }, raise_on_error=False)
            assert private_tree.is_error
            assert "filesystem_permission_denied" in private_tree.content[0].text
            hidden_parent = await bob_mcp.call_tool("list_filesystem_children", {"parent_id": alice_directory["id"]}, raise_on_error=False)
            assert hidden_parent.is_error
            assert "filesystem_permission_denied" in hidden_parent.content[0].text
            missing = bob.get(FILESYSTEM + "/nodes/" + str(uuid4()))
            assert missing.status_code == forbidden.status_code
            assert missing.json() == forbidden.json()
            discovered = await alice_mcp.call_tool("get_filesystem_node", {"node_id": uploaded["id"]})
            contents = await alice_mcp.read_resource(file_resource_link(discovered, uploaded["id"]))
            assert len(contents) == 1
            assert isinstance(contents[0], BlobResourceContents)
            assert base64.b64decode(contents[0].blob) == uploaded_bytes
            uploaded_path = FILESYSTEM + "/nodes/" + uploaded["id"]
            delete_headers = {"If-Match": '"' + str(uploaded["revision"]) + '"'}
            current_file = alice_second.get(uploaded_path)
            assert checked_summary(current_file, 200) == uploaded
            assert current_file.headers["etag"] == delete_headers["If-Match"]
            eligible = alice_second.options(uploaded_path)
            assert eligible.status_code == 204, eligible.text
            assert "DELETE" in {method.strip() for method in eligible.headers["allow"].split(",")}
            assert eligible.headers["cache-control"] == "no-store"
            assert bob.options(uploaded_path).status_code == 403
            assert alice_second.delete(uploaded_path).status_code == 428
            assert alice_second.delete(uploaded_path, headers={"If-Match": 'W/"1"'}).status_code == 422
            assert httpx.delete(runtime_endpoints.api_base_url + uploaded_path, headers=delete_headers, timeout=30).status_code == 401
            hidden_delete = bob.delete(uploaded_path, headers=delete_headers)
            absent_delete = bob.delete(FILESYSTEM + "/nodes/" + str(uuid4()), headers=delete_headers)
            assert hidden_delete.status_code == absent_delete.status_code == 403
            assert hidden_delete.json() == absent_delete.json()
            stale_delete = alice_second.delete(uploaded_path, headers={"If-Match": '"' + str(uploaded["revision"] + 1) + '"'})
            assert stale_delete.status_code == 412, stale_delete.text
            assert alice.get(uploaded_path + "/content").content == uploaded_bytes
            directory_path = FILESYSTEM + "/nodes/" + alice_directory["id"]
            directory_options = alice.options(directory_path)
            assert directory_options.status_code == 204
            assert "DELETE" not in {method.strip() for method in directory_options.headers["allow"].split(",")}
            assert alice.delete(directory_path, headers={"If-Match": '"' + str(alice_directory["revision"]) + '"'}).status_code == 409
            removed = alice_second.delete(uploaded_path, headers=delete_headers)
            assert removed.status_code == 204, removed.text
            assert removed.content == b""
            assert removed.headers["cache-control"] == "no-store"
            assert alice.get(uploaded_path).status_code == 403
            assert alice.get(uploaded_path + "/content").status_code == 403
            assert alice.get(uploaded_path + "/breadcrumbs").status_code == 403
            assert alice.options(uploaded_path).status_code == 403
            assert alice.delete(uploaded_path, headers=delete_headers).status_code == 403
            assert alice.post(upload["complete_url"]).status_code == 403
            assert {node["id"] for node in alice.get(directory_path + "/children").json()["nodes"]} == {alice_file["id"]}
            deleted_mcp = await alice_mcp.call_tool("get_filesystem_node", {"node_id": uploaded["id"]}, raise_on_error=False)
            assert deleted_mcp.is_error
            assert "filesystem_permission_denied" in deleted_mcp.content[0].text
            await check_mcp_file_deletion(alice, alice_second, alice_mcp, bob_mcp, alice_directory["id"], approvals)
            current_policy = alice.get(policy_url).json()
            revoked = alice.put(policy_url, json={"expected_revision": current_policy["revision"], "groups": []})
            assert revoked.status_code == 200, revoked.text
            assert revoked.json()["groups"] == []
            assert alice.get(FILESYSTEM + "/browse").status_code == 403
            assert bob.get(FILESYSTEM + "/browse").status_code == 403
            assert alice_second.get(FILESYSTEM + "/nodes/" + root["id"] + "/breadcrumbs").status_code == 403
            await wait_for_filesystem_tools(bob_mcp, {"get_filesystem_node"}, frozenset({"get_filesystem_root"}))
            revoked_root = await bob_mcp.call_tool("get_filesystem_root", {}, raise_on_error=False)
            assert revoked_root.is_error
            assert revoked_root.content[0].text == "Authorization failed for tool 'get_filesystem_root': not found or not authorized"
            assert checked_summary(alice_second.get(FILESYSTEM + "/nodes/" + alice_file["id"]), 200) == alice_file
            checked_breadcrumbs(alice_second.get(breadcrumb_path), [alice_directory], False)
            checked_breadcrumbs(
                alice_second.get(FILESYSTEM + "/nodes/" + alice_file["id"] + "/breadcrumbs"),
                [alice_directory, alice_file], False,
            )
            checked_breadcrumbs(bob.get(FILESYSTEM + "/nodes/" + bob_file["id"] + "/breadcrumbs"), [bob_file], False)
            assert tool_payload(await bob_mcp.call_tool("get_filesystem_node", {"node_id": bob_file["id"]})) == {
                **bob_file, "sharing": {"can_share": True, "grants": []},
            }
            contents = await bob_mcp.read_resource(bob_uri)
            assert len(contents) == 1
            assert isinstance(contents[0], TextResourceContents)
            assert contents[0].text == ""
            partial = tool_payload(await alice_mcp.call_tool("filesystem_browse", {
                "operation": "ls", "target": {"type": "node", "node_id": alice_directory["id"]},
            }))["result"]
            assert partial["breadcrumbs"]["complete"] is False
            assert {node["id"] for node in partial["entries"]} == {alice_file["id"]}
            stale = alice.put(policy_url, json={"expected_revision": current_policy["revision"], "groups": [group]})
            assert stale.status_code == 409
            assert stale.json()["detail"]["code"] == "filesystem_policy_stale"
            assert alice.get(FILESYSTEM + "/browse").status_code == 403
            await check_filesystem_descriptions(alice, alice_second, bob, alice_mcp, alice_directory["id"])
            await check_filesystem_node_updates(alice, alice_second, bob, alice_mcp, alice_directory["id"])


@pytest.mark.parametrize("method,suffix,body,status", [
    ("GET", "/root", {}, 404),
    ("OPTIONS", "/nodes/{id}/uploads", {}, 405),
    ("GET", "/nodes?scope=owned", {}, 404),
    ("GET", "/nodes?scope=shared", {}, 404),
    ("PUT", "/nodes/{id}/content", {}, 405),
    ("PATCH", "/nodes/{id}", {"name": "renamed"}, 403),
    ("PATCH", "/nodes/{id}", {"parent_id": str(uuid4())}, 403),
    ("PATCH", "/nodes/{id}/description", {"description": "obsolete endpoint"}, 404),
])
def test_removed_filesystem_routes_and_missing_node_updates_preserve_root_policy(
    runtime_endpoints: RuntimeEndpoints, method: str, suffix: str, body: dict[str, Any], status: int,
) -> None:
    path = FILESYSTEM + suffix.format(id=uuid4())
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers={
        "Authorization": "Bearer " + runtime_endpoints.bearer_token,
        "If-Match": '"1"',
    }, timeout=30) as client:
        before = client.get("/api/admin/filesystem/root-access")
        assert before.status_code == 200
        response = client.request(method, path, json=body)
        assert response.status_code == status, response.text
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
    "/api/me/profile", "/api/admin/openapi.json", "/api/me/catalogue",
    "/api/me/filesystem/browse", "/api/me/openapi.json", "/api/future-protected-route",
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


def test_upload_begin_checks_parent_permissions(
    runtime_endpoints: RuntimeEndpoints,
) -> None:
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers={
        "Authorization": "Bearer " + runtime_endpoints.bearer_token,
    }, timeout=30) as client:
        response = client.post(
            FILESYSTEM + "/nodes/" + str(uuid4()) + "/uploads",
            json={"name": "denied.bin", "metadata": {"content_type": "application/octet-stream", "attributes": {}}, "size_bytes": 1},
        )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "filesystem_permission_denied"
    assert response.headers["cache-control"] == "no-store"
