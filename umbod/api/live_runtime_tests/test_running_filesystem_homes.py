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
from mcp.shared.exceptions import MCPError

from conftest import RuntimeEndpoints
from test_running_filesystem import (
    FILESYSTEM, STRUCTURAL_ROOT, file_resource_uri, checked_breadcrumbs, checked_summary, node_identity, tool_payload, wait_for_filesystem_tools,
)
from test_running_personal_mcp_execution import mcp_client, proxy_token
from user_sharing_support import observed_recipient
from upload_transfer_support import assert_transfer_succeeded, transfer_upload


NAMESPACE_ADMIN = "/api/admin/filesystem/namespaces"


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
        assert api.get(FILESYSTEM + "/browse", params={"node_id": STRUCTURAL_ROOT}).status_code == 403
        assert other_api.get(FILESYSTEM + "/browse", params={"node_id": STRUCTURAL_ROOT}).status_code == 403
        token = proxy_token(runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, identity)
        second_token = proxy_token(second_mcp, runtime_endpoints.bearer_token, identity)
        other_token = proxy_token(second_mcp, other_bearer, identity)
        async with mcp_client(runtime_endpoints.mcp_url, token) as client, mcp_client(
            second_mcp, second_token,
        ) as second_client, mcp_client(second_mcp, other_token) as other_client:
            await wait_for_filesystem_tools(client, {"filesystem_browse"})
            await wait_for_filesystem_tools(other_client, {"filesystem_browse"})
            yield HomeRuntime(api, other_api, client, second_client, other_client)


def caller_namespaces(api: httpx.Client) -> list[dict[str, Any]]:
    response = api.get(FILESYSTEM + "/namespaces")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    namespaces = response.json()["namespaces"]
    assert namespaces[0]["kind"] == "personal"
    assert len([item for item in namespaces if item["kind"] == "personal"]) == 1
    assert all(set(item) == {"id", "root_node_id", "name", "description", "kind", "permissions"} for item in namespaces)
    return namespaces


@pytest.mark.asyncio
async def test_home_is_stable_private_and_independent_of_legacy_root_access(home_runtime: HomeRuntime) -> None:
    runtime = home_runtime
    responses = await asyncio.gather(*(
        client.call_tool("filesystem_browse", {"operation": "namespaces"})
        for client in (runtime.client, runtime.second_client)
    ))
    listings = [tool_payload(response)["result"]["namespaces"] for response in responses]
    assert listings[0] == listings[1] == caller_namespaces(runtime.api)
    personal = listings[0][0]
    assert set(personal["permissions"]) == {"discover", "read", "write", "delete"}
    responses = await asyncio.gather(*(
        client.call_tool("filesystem_browse", {"operation": "home"})
        for client in (runtime.client, runtime.second_client)
    ))
    homes = [tool_payload(response)["result"] for response in responses]
    assert homes[0] == homes[1]
    home = homes[0]["node"]
    assert home["id"] == personal["root_node_id"]
    assert home["permissions"] == {
        "can_discover": True, "can_read": True, "can_write": True, "can_delete": False, "can_share": False,
    }
    assert home["visible_to"] == {"type": "namespace", "namespace_id": personal["id"], "kind": "personal", "name": personal["name"]}
    assert homes[0]["breadcrumbs"] == {
        "items": [{key: home[key] for key in ("id", "name", "kind")}], "complete": True,
    }
    rest_home = checked_summary(runtime.api.post(FILESYSTEM + "/home"), 200)
    assert node_identity(rest_home) == node_identity(home)
    default = runtime.api.get(FILESYSTEM + "/browse")
    assert default.status_code == 200
    assert default.json()["node"] == rest_home
    for target in ({"type": "root"}, {"type": "path", "path": "/"}):
        inspected = tool_payload(await runtime.second_client.call_tool("filesystem_browse", {
            "operation": "stat", "target": target,
        }))["result"]
        assert inspected["node"]["id"] == home["id"]
        assert inspected["breadcrumbs"] == homes[0]["breadcrumbs"]
    other_personal = caller_namespaces(runtime.other_api)[0]
    assert other_personal["id"] != personal["id"]
    assert other_personal["root_node_id"] != home["id"]
    assert personal["id"] not in {item["id"] for item in caller_namespaces(runtime.other_api)}
    assert other_personal["id"] not in {item["id"] for item in caller_namespaces(runtime.api)}
    other_default = runtime.other_api.get(FILESYSTEM + "/browse")
    assert other_default.status_code == 200
    assert other_default.json()["node"]["id"] == other_personal["root_node_id"]
    home_path = FILESYSTEM + "/nodes/" + home["id"]
    denied = runtime.other_api.get(home_path)
    missing = runtime.other_api.get(FILESYSTEM + "/nodes/" + str(uuid4()))
    assert denied.status_code == missing.status_code == 403
    assert denied.json() == missing.json()
    child = checked_summary(runtime.api.post(home_path + "/directories", json={
        "name": "nested-" + uuid4().hex, "metadata": {"content_type": {}, "attributes": {}},
    }), 201)
    checked_breadcrumbs(runtime.api.get(FILESYSTEM + "/nodes/" + child["id"] + "/breadcrumbs"), [home, child], True)
    by_path = tool_payload(await runtime.second_client.call_tool("filesystem_browse", {
        "operation": "stat", "target": {"type": "path", "path": "/" + child["name"]},
    }))["result"]
    assert by_path["node"]["id"] == child["id"]
    assert by_path["breadcrumbs"]["complete"] is True
    for patch in ({"name": "renamed-" + uuid4().hex}, {"parent_id": child["id"]}):
        rejected = runtime.api.patch(home_path, headers={"If-Match": f'"{home["revision"]}"'}, json=patch)
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "filesystem_root_protected"
    assert runtime.api.delete(home_path, headers={"If-Match": f'"{home["revision"]}"'}).status_code == 409
    assert caller_namespaces(runtime.api)[0] == personal
    assert runtime.other_api.get(home_path).status_code == 403
    assert runtime.api.get(FILESYSTEM + "/nodes/" + other_personal["root_node_id"]).status_code == 403
    assert runtime.api.get(FILESYSTEM + "/browse").json()["node"] == rest_home


@pytest.mark.asyncio
async def test_personal_upload_preserves_receipt_bytes_and_owner_sharing(home_runtime: HomeRuntime) -> None:
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
    with httpx.Client(timeout=30, follow_redirects=False) as anonymous:
        assert_transfer_succeeded(transfer_upload(anonymous, begun["transfer"], data))
    await wait_for_filesystem_tools(runtime.second_client, {"filesystem_complete_upload"})
    receipt = tool_payload(await runtime.second_client.call_tool("filesystem_complete_upload", {"upload_id": begun["upload_id"]}))
    file = receipt["node"]
    assert file["parent_id"] == home["id"]
    assert receipt["size_bytes"] == len(data)
    assert receipt["sha256"] == digest
    assert file["permissions"]["can_write"] is True
    assert file["permissions"]["can_delete"] is True
    assert file["visible_to"] == home["visible_to"]
    path = FILESYSTEM + "/nodes/" + file["id"]
    downloaded = runtime.api.get(path + "/content?delivery=stream")
    assert downloaded.status_code == 200
    assert downloaded.content == data
    assert runtime.other_api.get(path).status_code == 403
    assert runtime.api.get(path + "/access").status_code == 200
    assert file["permissions"]["can_share"] is True
    assert runtime.other_api.get(path + "/content?delivery=stream").status_code == 403
    replayed = tool_payload(await runtime.client.call_tool("filesystem_complete_upload", {"upload_id": begun["upload_id"]}))
    assert replayed == receipt
    assert runtime.api.get(path + "/content?delivery=stream").content == data


def save_namespace(api: httpx.Client, namespace: dict[str, Any], groups: list[dict[str, str]]) -> dict[str, Any]:
    response = api.put(NAMESPACE_ADMIN + "/" + namespace["id"], json={
        "expected_revision": namespace["revision"], "name": namespace["name"], "groups": groups,
    })
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    updated = response.json()
    assert updated["revision"] == namespace["revision"] + 1
    assert updated["root_node_id"] == namespace["root_node_id"]
    assert updated["groups"] == groups
    assert updated["description"] == namespace["description"]
    assert updated["root_revision"] == namespace["root_revision"]
    return updated


@pytest.mark.asyncio
async def test_one_namespace_can_be_created_before_groups_and_shared_by_multiple_groups_across_workers(home_runtime: HomeRuntime) -> None:
    runtime = home_runtime
    created = runtime.api.post(NAMESPACE_ADMIN, json={"name": "independent-" + uuid4().hex, "groups": []})
    assert created.status_code == 201, created.text
    namespace = created.json()
    namespace_id = namespace["id"]
    root_id = namespace["root_node_id"]
    assert namespace["groups"] == []
    registered: list[str] = []
    try:
        for prefix in ("namespace-readers-", "namespace-writers-"):
            group_id = prefix + uuid4().hex
            response = runtime.api.post("/api/admin/groups", json={"group_id": group_id})
            assert response.status_code == 204, response.text
            registered.append(group_id)
        grants = [{"group_id": registered[0], "access": "read"}, {"group_id": registered[1], "access": "read_write"}]
        namespace = save_namespace(runtime.api, namespace, grants)
        observed = runtime.other_api.get(NAMESPACE_ADMIN)
        assert observed.status_code == 200, observed.text
        matches = [entry for entry in observed.json()["namespaces"] if entry["id"] == namespace_id]
        assert matches == [namespace]
        assert namespace["root_node_id"] == root_id
        assert namespace["groups"] == grants
        for api in (runtime.api, runtime.other_api):
            assert api.get(FILESYSTEM + "/nodes/" + root_id).status_code == 403
        namespace = save_namespace(runtime.other_api, namespace, [grants[1]])
        assert namespace["id"] == namespace_id
        assert namespace["root_node_id"] == root_id
        assert namespace["groups"] == [grants[1]]
    finally:
        save_namespace(runtime.api, namespace, [])
        for group_id in registered:
            response = runtime.api.delete("/api/admin/groups/" + group_id)
            assert response.status_code == 204, response.text


@pytest.mark.asyncio
async def test_shared_namespace_policy_is_authoritative_across_workers_and_pending_uploads(
    home_runtime: HomeRuntime, request: pytest.FixtureRequest,
) -> None:
    runtime = home_runtime
    groups = runtime.api.get("/api/admin/groups")
    assert groups.status_code == 200
    group_existed = any(group["group_id"] == "admin" for group in groups.json()["groups"])
    assert runtime.api.post("/api/admin/groups", json={"group_id": "admin"}).status_code == 204

    def remove_created_group() -> None:
        if not group_existed:
            removed = runtime.api.delete("/api/admin/groups/admin")
            assert removed.status_code == 204, removed.text

    request.addfinalizer(remove_created_group)
    file_id: str | None = None
    description = 'Shared project <scope>\nUse for team "drafts" 東京.'
    created = runtime.api.post(NAMESPACE_ADMIN, json={"name": "runtime-shared-" + uuid4().hex, "description": description, "groups": []})
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    namespace = created.json()
    assert set(namespace) == {"id", "root_node_id", "name", "description", "revision", "root_revision", "groups"}
    assert namespace["description"] == description
    assert type(namespace["revision"]) is int and namespace["revision"] > 0
    try:
        management = runtime.api.get(NAMESPACE_ADMIN)
        assert management.status_code == 200
        assert management.headers["cache-control"] == "no-store"
        assert namespace in management.json()["namespaces"]
        assert namespace["id"] not in {item["id"] for item in caller_namespaces(runtime.api)}
        root_path = FILESYSTEM + "/nodes/" + namespace["root_node_id"]
        assert runtime.api.get(root_path).status_code == 403
        namespace = save_namespace(runtime.api, namespace, [{"group_id": "admin", "access": "read_write"}])
        summaries = caller_namespaces(runtime.api)
        shared = next(item for item in summaries if item["id"] == namespace["id"])
        assert shared["kind"] == "shared"
        assert shared["root_node_id"] == namespace["root_node_id"]
        assert shared["description"] == description
        assert set(shared["permissions"]) == {"discover", "read", "write", "delete"}
        assert summaries[1:] == sorted(summaries[1:], key=lambda item: item["name"])
        mcp_namespaces = tool_payload(await runtime.second_client.call_tool("filesystem_browse", {"operation": "namespaces"}))
        assert mcp_namespaces["result"]["namespaces"] == summaries
        assert shared in caller_namespaces(runtime.other_api)
        root = checked_summary(runtime.api.get(root_path), 200)
        assert root["metadata"]["attributes"]["description"] == description
        assert root["revision"] == namespace["root_revision"]
        mcp_root = tool_payload(await runtime.second_client.call_tool("filesystem_browse", {
            "operation": "stat", "target": {"type": "node", "node_id": root["id"]},
        }))["result"]["node"]
        assert mcp_root["metadata"]["attributes"]["description"] == description
        for patch in ({"name": "forbidden-root-name"}, {"parent_id": caller_namespaces(runtime.api)[0]["root_node_id"]}):
            protected = runtime.api.patch(root_path, headers={"If-Match": f'"{root["revision"]}"'}, json=patch)
            assert protected.status_code == 409
            assert protected.json()["detail"]["code"] == "filesystem_root_protected"
        assert runtime.api.delete(root_path, headers={"If-Match": f'"{root["revision"]}"'}).status_code == 409
        assert runtime.api.get(root_path + "/access").status_code == 403
        await wait_for_filesystem_tools(runtime.client, {"create_filesystem_directory", "filesystem_upload"})
        directory = tool_payload(await runtime.client.call_tool("create_filesystem_directory", {
            "parent_id": namespace["root_node_id"], "name": "shared-directory", "metadata": {"content_type": {}, "attributes": {}},
        }))
        data = "Shared bytes 東京\n"
        file = tool_payload(await runtime.client.call_tool("filesystem_upload", {
            "parent_id": directory["id"], "name": "shared.txt", "metadata": {"content_type": "text/plain", "attributes": {}},
            "content": {"encoding": "utf-8", "text": data},
        }))
        file_id = file["id"]
        file_path = FILESYSTEM + "/nodes/" + file["id"]
        access = runtime.api.get(file_path + "/access")
        assert access.status_code == 200
        narrow = runtime.api.put(file_path + "/access", params={"recipient_type": "group"}, headers={"If-Match": access.headers["etag"]}, json={
            "grants": [{"recipient": {"type": "group", "group_id": "admin"}, "permissions": ["discover", "read"]}],
        })
        assert narrow.status_code == 200, narrow.text
        assert runtime.other_api.get(file_path).json()["permissions"]["can_write"] is True
        clear = runtime.api.put(file_path + "/access", params={"recipient_type": "group"}, headers={"If-Match": narrow.headers["etag"]}, json={"grants": []})
        assert clear.status_code == 200
        assert runtime.other_api.get(file_path).json()["permissions"]["can_write"] is True
        assert runtime.api.get(file_path + "/access").status_code == 200
        read = runtime.other_api.get(file_path + "/content?delivery=stream")
        assert read.status_code == 200
        assert read.content == data.encode()
        inspected = tool_payload(await runtime.other_client.call_tool("filesystem_browse", {
            "operation": "stat", "target": {"type": "node", "node_id": file["id"]},
        }))["result"]
        assert inspected["node"]["permissions"]["can_share"] is False
        assert inspected["breadcrumbs"]["complete"] is True
        assert [item["id"] for item in inspected["breadcrumbs"]["items"]] == [namespace["root_node_id"], directory["id"], file["id"]]
        personal = caller_namespaces(runtime.api)[0]
        crossing = runtime.api.patch(file_path, headers={"If-Match": f'"{file["revision"]}"'}, json={"parent_id": personal["root_node_id"]})
        assert crossing.status_code == 409
        assert crossing.json()["detail"]["code"] == "filesystem_invalid_move"
        assert runtime.api.get(file_path).json()["parent_id"] == directory["id"]
        pending = runtime.api.post(root_path + "/uploads", json={
            "name": "pending.bin", "size_bytes": 3, "metadata": {"content_type": "application/octet-stream", "attributes": {}},
        })
        assert pending.status_code == 201
        upload = pending.json()
        assert_transfer_succeeded(transfer_upload(runtime.api, upload["transfer"], b"abc"))
        stale_revision = namespace["revision"]
        namespace = save_namespace(runtime.api, namespace, [{"group_id": "admin", "access": "read"}])
        stale = runtime.other_api.put(NAMESPACE_ADMIN + "/" + namespace["id"], json={
            "expected_revision": stale_revision, "name": namespace["name"], "groups": [],
        })
        assert stale.status_code == 409
        assert stale.headers["cache-control"] == "no-store"
        policies = runtime.other_api.get(NAMESPACE_ADMIN)
        assert policies.status_code == 200
        assert namespace in policies.json()["namespaces"]
        reader = checked_summary(runtime.other_api.get(file_path), 200)
        assert reader["permissions"]["can_read"] is True
        assert reader["permissions"]["can_write"] is False
        assert reader["permissions"]["can_delete"] is False
        assert runtime.other_api.patch(file_path, headers={"If-Match": f'"{reader["revision"]}"'}, json={"name": "forbidden.txt"}).status_code == 403
        assert runtime.other_api.delete(file_path, headers={"If-Match": f'"{reader["revision"]}"'}).status_code == 403
        assert runtime.api.post(root_path + "/directories", json={
            "name": "forbidden", "metadata": {"content_type": {}, "attributes": {}},
        }).status_code == 403
        assert runtime.other_api.get(file_path + "/access").status_code == 403
        assert runtime.api.get(file_path + "/access").status_code == 200
        assert runtime.api.get(file_path).json()["permissions"]["can_write"] is True
        assert runtime.api.post(upload["complete_url"]).status_code == 403
        still_readable = runtime.other_api.get(file_path + "/content?delivery=stream")
        assert still_readable.status_code == 200
        assert still_readable.content == data.encode()
        resources = await runtime.other_client.read_resource(file_resource_uri(file["id"]))
        assert len(resources) == 1
        assert resources[0].text == data
        denied_write = await runtime.other_client.call_tool("update_filesystem_node", {
            "node_id": file["id"], "expected_revision": file["revision"], "name": "forbidden-via-mcp",
        }, raise_on_error=False)
        assert denied_write.is_error
        assert "filesystem_permission_denied" in denied_write.content[0].text
        namespace = save_namespace(runtime.api, namespace, [])
        for api in (runtime.api, runtime.other_api):
            assert api.get(root_path).status_code == 403
            assert namespace["id"] not in {item["id"] for item in caller_namespaces(api)}
            assert api.get(FILESYSTEM + "/browse").status_code == 200
        assert runtime.api.post(upload["complete_url"]).status_code == 403
        assert runtime.other_api.get(file_path).status_code == 403
        assert runtime.other_api.get(file_path + "/content?delivery=stream").status_code == 403
        assert runtime.api.get(file_path).status_code == 200
        assert runtime.api.get(file_path + "/content?delivery=stream").content == data.encode()
        rejected = await runtime.other_client.call_tool("filesystem_browse", {
            "operation": "stat", "target": {"type": "node", "node_id": file["id"]},
        }, raise_on_error=False)
        assert rejected.is_error
        assert "filesystem_permission_denied" in rejected.content[0].text
        with pytest.raises(MCPError) as revoked_resource:
            await runtime.other_client.read_resource(file_resource_uri(file["id"]))
        with pytest.raises(MCPError) as unknown_resource:
            await runtime.other_client.read_resource(file_resource_uri(str(uuid4())))
        assert revoked_resource.value.error.message == unknown_resource.value.error.message
        assert runtime.other_api.post("/api/me/identity-observations").status_code == 204
        claims = jwt.decode(os.environ["UMBOD_TEST_BEARER_TOKEN_B"], options={"verify_signature": False})
        recipient = await observed_recipient(runtime.client, file["id"], claims["name"])
        access = runtime.api.get(file_path + "/access")
        shared_again = runtime.api.put(file_path + "/access", params={"recipient_type": "user"}, headers={"If-Match": access.headers["etag"]}, json={
            "grants": [{"recipient": {"type": "user", "user_id": recipient["user_id"]}, "permissions": ["discover", "read"]}],
        })
        assert shared_again.status_code == 200
        namespace = save_namespace(runtime.api, namespace, [{"group_id": "admin", "access": "read"}])
        assert namespace["id"] in {item["id"] for item in caller_namespaces(runtime.other_api)}
        namespace = save_namespace(runtime.api, namespace, [])
        assert namespace["id"] not in {item["id"] for item in caller_namespaces(runtime.other_api)}
        assert runtime.other_api.get(root_path).status_code == 403
        assert runtime.other_api.get(file_path + "/content?delivery=stream").content == data.encode()
        resources = await runtime.other_client.read_resource(file_resource_uri(file["id"]))
        assert resources[0].text == data
        current_access = runtime.api.get(file_path + "/access")
        assert current_access.status_code == 200
        revoked_again = runtime.api.put(file_path + "/access", params={"recipient_type": "user"}, headers={"If-Match": current_access.headers["etag"]}, json={"grants": []})
        assert revoked_again.status_code == 200
        assert runtime.other_api.get(file_path).status_code == 403
    finally:
        if file_id is not None:
            for recipient_type in ("user", "group"):
                access = runtime.api.get(FILESYSTEM + "/nodes/" + file_id + "/access")
                assert access.status_code == 200
                cleared = runtime.api.put(FILESYSTEM + "/nodes/" + file_id + "/access", params={"recipient_type": recipient_type}, headers={"If-Match": access.headers["etag"]}, json={"grants": []})
                assert cleared.status_code == 200
        current = runtime.api.get(NAMESPACE_ADMIN)
        assert current.status_code == 200
        namespace = next(item for item in current.json()["namespaces"] if item["id"] == namespace["id"])
        save_namespace(runtime.api, namespace, [])
