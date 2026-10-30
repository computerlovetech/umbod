import base64
import json
import os
import ssl
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastmcp import Client
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


def checked_breadcrumbs(
    response: httpx.Response, nodes: list[dict[str, Any]], complete: bool,
) -> None:
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [{field: node[field] for field in ("id", "name", "kind")} for node in nodes],
        "complete": complete,
    }


async def check_mcp_file_deletion(
    alice: httpx.Client, alice_second: httpx.Client,
    alice_mcp: Client[Any], bob_mcp: Client[Any], parent_id: str,
) -> None:
    parent_path = FILESYSTEM + "/nodes/" + parent_id
    children_before = alice.get(parent_path + "/children").json()["nodes"]
    data = b"delete through MCP"
    started = alice.post(parent_path + "/uploads", json={
        "name": "mcp-delete-" + uuid4().hex,
        "metadata": {"content_type": "text/plain", "attributes": {}},
        "size_bytes": len(data),
    })
    assert started.status_code == 201, started.text
    upload = started.json()
    transferred = alice_second.put(
        upload["transfer"]["url"], content=data, headers=upload["transfer"]["headers"],
    )
    assert transferred.status_code == 204, transferred.text
    node = checked_summary(alice_second.post(upload["complete_url"]), 201)
    node_path = FILESYSTEM + "/nodes/" + node["id"]
    read_arguments = {"node_id": node["id"], "encoding": "utf-8", "max_bytes": len(data)}
    assert tool_payload(await alice_mcp.call_tool("filesystem_read_file", read_arguments)) == {
        "node_id": node["id"], "revision": node["revision"], "size_bytes": len(data),
        "content": {"encoding": "utf-8", "text": data.decode("utf-8")},
    }
    denied_read = await bob_mcp.call_tool("filesystem_read_file", read_arguments, raise_on_error=False)
    missing_read = await bob_mcp.call_tool("filesystem_read_file", {
        "node_id": str(uuid4()), "encoding": "utf-8", "max_bytes": len(data),
    }, raise_on_error=False)
    assert denied_read.is_error and missing_read.is_error
    assert denied_read.content[0].text == missing_read.content[0].text
    assert "filesystem_permission_denied" in denied_read.content[0].text
    read_directory = await alice_mcp.call_tool("filesystem_read_file", {
        "node_id": parent_id, "encoding": "utf-8", "max_bytes": 1_048_576,
    }, raise_on_error=False)
    assert read_directory.is_error
    assert "filesystem_wrong_node_kind" in read_directory.content[0].text
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
    assert tool_payload(await alice_mcp.call_tool("filesystem_delete_file", arguments)) == {
        "node_id": node["id"], "deleted": True,
    }
    assert alice.get(node_path).status_code == 403
    assert alice_second.get(node_path).status_code == 403
    assert alice.get(node_path + "/content").status_code == 403
    assert alice_second.post(upload["complete_url"]).status_code == 403
    deleted_read = await alice_mcp.call_tool("filesystem_read_file", read_arguments, raise_on_error=False)
    assert deleted_read.is_error
    assert "filesystem_permission_denied" in deleted_read.content[0].text
    assert alice.get(parent_path + "/children").json()["nodes"] == children_before
    repeated = await alice_mcp.call_tool("filesystem_delete_file", arguments, raise_on_error=False)
    assert repeated.is_error
    assert "filesystem_permission_denied" in repeated.content[0].text


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
        assert set(policy) == {"status", "revision", "groups", "blocked_group_ids"}
        assert policy["blocked_group_ids"] == []
        group = {"group_id": "admin", "permissions": ["discover", "write"]}
        configured = alice.put(policy_url, json={"expected_revision": policy["revision"], "groups": [group]})
        assert configured.status_code == 200, configured.text
        assert configured.headers["cache-control"] == "no-store"
        assert set(configured.json()) == {"status", "revision", "groups", "blocked_group_ids"}
        assert configured.json()["status"] == "ready"
        root = checked_summary(alice.get(FILESYSTEM + "/root"), 200)
        assert checked_summary(bob.get(FILESYSTEM + "/root"), 200) == root
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
        assert allowed.status_code == 204, allowed.text
        assert {method.strip() for method in allowed.headers["allow"].split(",")} == {"POST", "OPTIONS"}
        assert bob.options(uploads_path).status_code == 403
        denied_upload = bob.post(uploads_path, json=upload_request)
        assert denied_upload.status_code == 403
        assert denied_upload.json()["detail"]["code"] == "filesystem_permission_denied"
        begun = alice.post(uploads_path, json=upload_request)
        assert begun.status_code == 201, begun.text
        assert begun.headers["cache-control"] == "no-store"
        upload = begun.json()
        assert upload["transfer"]["type"] == "single"
        assert upload["transfer"]["method"] == "PUT"
        assert upload["transfer"]["authorization"] == {"type": "same_origin"}
        session = alice_second.get(begun.headers["location"])
        assert session.status_code == 200, session.text
        assert session.json()["status"] == "pending"
        assert bob.get(begun.headers["location"]).status_code == 403
        assert bob.put(upload["transfer"]["url"], content=uploaded_bytes).status_code == 403
        assert bob.post(upload["complete_url"]).status_code == 403
        assert alice_second.post(upload["complete_url"]).status_code == 409
        transferred = alice_second.put(
            upload["transfer"]["url"], content=uploaded_bytes,
            headers=upload["transfer"]["headers"],
        )
        assert transferred.status_code == 204, transferred.text
        assert alice.get(begun.headers["location"]).json()["status"] == "uploaded"
        assert alice.get(FILESYSTEM + "/nodes/" + alice_directory["id"] + "/children").json()["nodes"] == []
        completed = alice.post(upload["complete_url"])
        uploaded = checked_summary(completed, 201)
        assert completed.headers["location"] == FILESYSTEM + "/nodes/" + uploaded["id"]
        assert checked_summary(alice_second.post(upload["complete_url"]), 200) == uploaded
        checked_breadcrumbs(
            alice_second.get(FILESYSTEM + "/nodes/" + uploaded["id"] + "/breadcrumbs"),
            [root, alice_directory, uploaded], True,
        )
        assert alice_second.get(begun.headers["location"]).json()["status"] == "completed"
        assert alice.put(
            upload["transfer"]["url"], content=uploaded_bytes,
            headers=upload["transfer"]["headers"],
        ).status_code == 409
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
        async with mcp_client(second_mcp, alice_token) as alice_mcp, mcp_client(runtime_endpoints.mcp_url, bob_token) as bob_mcp:
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
            bob_file = tool_payload(await bob_mcp.call_tool("create_filesystem_file", {"parent_id": root["id"], "name": "bob-" + uuid4().hex, "metadata": metadata}))
            assert checked_summary(bob.get(FILESYSTEM + "/nodes/" + bob_file["id"]), 200) == bob_file
            forbidden = alice.get(FILESYSTEM + "/nodes/" + bob_file["id"])
            assert forbidden.status_code == 403
            assert forbidden.json()["detail"]["code"] == "filesystem_permission_denied"
            alice_file = tool_payload(await alice_mcp.call_tool("create_filesystem_file", {"parent_id": alice_directory["id"], "name": "draft", "metadata": metadata}))
            assert checked_summary(alice_second.get(FILESYSTEM + "/nodes/" + alice_file["id"]), 200) == alice_file
            child_response = alice.get(FILESYSTEM + "/nodes/" + alice_directory["id"] + "/children")
            assert child_response.status_code == 200
            assert {node["id"] for node in child_response.json()["nodes"]} == {alice_file["id"], uploaded["id"]}
            assert child_response.headers["cache-control"] == "no-store"
            browse_target = {"type": "path", "path": "/" + name}
            listed = tool_payload(await alice_mcp.call_tool("filesystem_browse", {
                "operation": "ls", "target": browse_target,
            }))["result"]
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
            read_arguments = {"node_id": uploaded["id"], "encoding": "base64", "max_bytes": len(uploaded_bytes)}
            assert tool_payload(await alice_mcp.call_tool("filesystem_read_file", read_arguments)) == {
                "node_id": uploaded["id"], "revision": uploaded["revision"], "size_bytes": len(uploaded_bytes),
                "content": {"encoding": "base64", "data": base64.b64encode(uploaded_bytes).decode("ascii")},
            }
            invalid_text = await alice_mcp.call_tool("filesystem_read_file", {
                **read_arguments, "encoding": "utf-8",
            }, raise_on_error=False)
            assert invalid_text.is_error
            assert "filesystem_read_invalid_encoding" in invalid_text.content[0].text
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
            assert alice.options(directory_path).status_code == 409
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
            await check_mcp_file_deletion(alice, alice_second, alice_mcp, bob_mcp, alice_directory["id"])
            current_policy = alice.get(policy_url).json()
            revoked = alice.put(policy_url, json={"expected_revision": current_policy["revision"], "groups": []})
            assert revoked.status_code == 200, revoked.text
            assert revoked.json()["groups"] == []
            assert alice.get(FILESYSTEM + "/root").status_code == 403
            assert bob.get(FILESYSTEM + "/root").status_code == 403
            assert alice_second.get(FILESYSTEM + "/nodes/" + root["id"] + "/breadcrumbs").status_code == 403
            revoked_root = await bob_mcp.call_tool("get_filesystem_root", {}, raise_on_error=False)
            assert revoked_root.is_error
            assert "filesystem_permission_denied" in revoked_root.content[0].text
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
            assert tool_payload(await bob_mcp.call_tool("filesystem_read_file", {
                "node_id": bob_file["id"], "encoding": "utf-8", "max_bytes": 0,
            })) == {
                "node_id": bob_file["id"], "revision": bob_file["revision"], "size_bytes": 0,
                "content": {"encoding": "utf-8", "text": ""},
            }
            partial = tool_payload(await alice_mcp.call_tool("filesystem_browse", {
                "operation": "ls", "target": {"type": "node", "node_id": alice_directory["id"]},
            }))["result"]
            assert partial["breadcrumbs"]["complete"] is False
            assert {node["id"] for node in partial["entries"]} == {alice_file["id"]}
            stale = alice.put(policy_url, json={"expected_revision": current_policy["revision"], "groups": [group]})
            assert stale.status_code == 409
            assert stale.json()["detail"]["code"] == "filesystem_policy_stale"
            assert alice.get(FILESYSTEM + "/root").status_code == 403


@pytest.mark.parametrize("method,suffix,body", [
    ("GET", "/nodes?scope=owned", {}),
    ("GET", "/nodes?scope=shared", {}),
    ("PUT", "/nodes/{id}/content", {}),
    ("PATCH", "/nodes/{id}", {"name": "renamed"}),
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
