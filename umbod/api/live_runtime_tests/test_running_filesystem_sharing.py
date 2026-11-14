import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
from mcp.shared.exceptions import MCPError
from mcp.types import TextResourceContents

from test_running_filesystem import (
    FILESYSTEM, STRUCTURAL_ROOT, checked_summary, file_resource_uri,
    sharing_write_payload, tool_payload, wait_for_filesystem_tools,
)
from test_running_filesystem_homes import HomeRuntime, home_runtime as home_runtime
from user_sharing_support import assert_mcp_user_target_sharing, assert_rest_recipient_scopes, observed_recipient


@dataclass
class SharingRuntime:
    home: HomeRuntime
    directory: dict[str, Any]
    recipient: dict[str, str]
    group_existed: bool


def replace_access(api: httpx.Client, node_id: str, recipient_type: str, grants: list[dict[str, Any]]) -> httpx.Response:
    path = FILESYSTEM + "/nodes/" + node_id + "/access"
    current = api.get(path)
    assert current.status_code == 200, current.text
    return api.put(path, params={"recipient_type": recipient_type}, headers={"If-Match": current.headers["etag"]}, json={"grants": grants})


@pytest_asyncio.fixture
async def sharing_runtime(home_runtime: HomeRuntime) -> AsyncIterator[SharingRuntime]:
    runtime = home_runtime
    groups = runtime.api.get("/api/admin/groups")
    assert groups.status_code == 200
    group_existed = any(group["group_id"] == "admin" for group in groups.json()["groups"])
    assert runtime.api.post("/api/admin/groups", json={"group_id": "admin"}).status_code == 204
    owned_nodes: list[str] = []
    try:
        personal = checked_summary(runtime.api.post(FILESYSTEM + "/home"), 200)
        directory = checked_summary(runtime.api.post(FILESYSTEM + "/nodes/" + personal["id"] + "/directories", json={
            "name": "item-sharing-" + uuid4().hex, "metadata": {"content_type": {}, "attributes": {}},
        }), 201)
        owned_nodes.append(directory["id"])
        assert runtime.other_api.post("/api/me/identity-observations").status_code == 204
        claims = jwt.decode(os.environ["UMBOD_TEST_BEARER_TOKEN_B"], options={"verify_signature": False})
        await wait_for_filesystem_tools(runtime.client, {"filesystem_share", "filesystem_search_sharing_recipients"})
        recipient = await observed_recipient(runtime.client, directory["id"], claims["name"])
        yield SharingRuntime(runtime, directory, recipient, group_existed)
    finally:
        for node_id in owned_nodes:
            for recipient_type in ("group", "user"):
                cleared = replace_access(runtime.api, node_id, recipient_type, [])
                assert cleared.status_code == 200, cleared.text
        if not group_existed:
            assert runtime.api.delete("/api/admin/groups/admin").status_code == 204


@pytest.mark.asyncio
async def test_personal_child_user_shares_cross_workers_without_namespace_membership(sharing_runtime: SharingRuntime) -> None:
    runtime = sharing_runtime.home
    directory = sharing_runtime.directory
    created = await runtime.client.call_tool("filesystem_upload", {
        "parent_id": directory["id"], "name": "direct-user.txt",
        "metadata": {"content_type": "text/plain", "attributes": {}},
        "content": {"encoding": "utf-8", "text": "Original personal bytes 東京\n"},
    })
    node = tool_payload(created)
    path = FILESYSTEM + "/nodes/" + node["id"]
    try:
        assert runtime.other_api.get(path).status_code == 403
        assert runtime.other_api.get(FILESYSTEM + "/nodes/" + directory["id"]).status_code == 403
        search = runtime.api.get(path + "/access/recipients", params={"query": sharing_runtime.recipient["label"], "recipient_type": "user"})
        assert search.status_code == 200
        assert sharing_runtime.recipient in search.json()["recipients"]
        recipient = {"type": "user", "user_id": sharing_runtime.recipient["user_id"]}
        shared = replace_access(runtime.api, node["id"], "user", [{"recipient": recipient, "permissions": ["discover", "read"]}])
        assert shared.status_code == 200, shared.text
        assert runtime.other_api.get(path + "/content?delivery=stream").content == "Original personal bytes 東京\n".encode()
        inspected = tool_payload(await runtime.other_client.call_tool("get_filesystem_node", {"node_id": node["id"]}))
        assert inspected["permissions"]["can_read"] is True
        assert inspected["permissions"]["can_share"] is False
        assert inspected["sharing"] == {"can_share": False}
        assert runtime.other_api.get(FILESYSTEM + "/nodes/" + directory["id"]).status_code == 403
        assert directory["parent_id"] not in {entry["root_node_id"] for entry in runtime.other_api.get(FILESYSTEM + "/namespaces").json()["namespaces"]}
        resources = await runtime.other_client.read_resource(file_resource_uri(node["id"]))
        assert len(resources) == 1 and isinstance(resources[0], TextResourceContents)
        assert resources[0].text == "Original personal bytes 東京\n"
        revoked = replace_access(runtime.api, node["id"], "user", [])
        assert revoked.status_code == 200
        assert runtime.other_api.get(path).status_code == 403
        rejected = await runtime.other_client.call_tool("get_filesystem_node", {"node_id": node["id"]}, raise_on_error=False)
        assert rejected.is_error
        with pytest.raises(MCPError):
            await runtime.other_client.read_resource(file_resource_uri(node["id"]))
        await assert_mcp_user_target_sharing(runtime.client, runtime.other_client, node["id"], sharing_runtime.recipient)
        assert_rest_recipient_scopes(runtime.api, runtime.other_api, path, sharing_runtime.recipient)
        assert runtime.api.get(path + "/content?delivery=stream").content == "Original personal bytes 東京\n".encode()
    finally:
        for recipient_type in ("group", "user"):
            assert replace_access(runtime.api, node["id"], recipient_type, []).status_code == 200


@pytest.mark.asyncio
async def test_recursive_personal_folder_share_does_not_grant_namespace_or_sibling_access(sharing_runtime: SharingRuntime) -> None:
    runtime = sharing_runtime.home
    folder = sharing_runtime.directory
    child = tool_payload(await runtime.client.call_tool("filesystem_upload", {
        "parent_id": folder["id"], "name": "recursive.txt",
        "metadata": {"content_type": "text/plain", "attributes": {}},
        "content": {"encoding": "utf-8", "text": "Inherited original bytes"},
    }))
    sibling = checked_summary(runtime.api.post(FILESYSTEM + "/nodes/" + folder["parent_id"] + "/directories", json={
        "name": "unshared-sibling-" + uuid4().hex, "metadata": {"content_type": {}, "attributes": {}},
    }), 201)
    target = {"type": "user", "user_id": sharing_runtime.recipient["user_id"]}
    command = {"node_id": folder["id"], "recipient": target, "permissions": ["discover", "read"], "recursive": True}
    shared = sharing_write_payload(await runtime.client.call_tool("filesystem_share", command))
    assert shared == {**command, "changed": True}
    repeated = sharing_write_payload(await runtime.client.call_tool("filesystem_share", command))
    assert repeated == {**command, "changed": False}
    for node in (folder, child):
        assert runtime.other_api.get(FILESYSTEM + "/nodes/" + node["id"]).status_code == 200
    assert runtime.other_api.get(FILESYSTEM + "/nodes/" + sibling["id"]).status_code == 403
    assert runtime.other_api.get(FILESYSTEM + "/nodes/" + folder["parent_id"]).status_code == 403
    assert runtime.other_api.get(FILESYSTEM + "/browse", params={"node_id": STRUCTURAL_ROOT}).status_code == 403
    resources = await runtime.other_client.read_resource(file_resource_uri(child["id"]))
    assert resources[0].text == "Inherited original bytes"
    assert replace_access(runtime.api, folder["id"], "user", []).status_code == 200
    assert runtime.other_api.get(FILESYSTEM + "/nodes/" + child["id"]).status_code == 403
    rejected = await runtime.other_client.call_tool("get_filesystem_node", {"node_id": child["id"]}, raise_on_error=False)
    assert rejected.is_error
    with pytest.raises(MCPError):
        await runtime.other_client.read_resource(file_resource_uri(child["id"]))


@pytest.mark.asyncio
async def test_namespace_roots_cannot_be_shared_but_children_can(sharing_runtime: SharingRuntime) -> None:
    runtime = sharing_runtime.home
    personal = sharing_runtime.directory["parent_id"]
    for node_id in (personal, STRUCTURAL_ROOT):
        path = FILESYSTEM + "/nodes/" + node_id + "/access"
        assert runtime.api.get(path).status_code == 403
        assert runtime.api.get(path + "/recipients", params={"query": "admin"}).status_code == 403
        assert runtime.api.put(path, params={"recipient_type": "group"}, headers={"If-Match": '"opaque"'}, json={"grants": []}).status_code == 403
        denied = await runtime.client.call_tool("filesystem_share", {
            "node_id": node_id, "group_id": "admin", "permissions": ["discover", "read"], "recursive": True,
        }, raise_on_error=False)
        assert denied.is_error
    assert runtime.api.get(FILESYSTEM + "/nodes/" + sharing_runtime.directory["id"] + "/access").status_code == 200
