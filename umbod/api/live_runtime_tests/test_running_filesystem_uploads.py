import base64
import hashlib
import json
import os
import ssl
import subprocess
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastmcp import Client
from mcp.shared.exceptions import MCPError
from mcp.types import BlobResourceContents, TextResourceContents

from conftest import RuntimeEndpoints
from test_running_filesystem import (
    FILESYSTEM, checked_root_browse, checked_summary, file_resource_link, file_resource_uri, tool_payload, wait_for_filesystem_tools,
)
from test_running_personal_mcp_execution import mcp_client, proxy_token
from upload_transfer_support import assert_s3_transfer, assert_transfer_succeeded, s3_runtime, transfer_upload


@dataclass
class NativeUploadRuntime:
    api: httpx.Client
    other_api: httpx.Client
    client: Client
    other_client: Client
    directory_id: str


@pytest_asyncio.fixture
async def native_upload_runtime(runtime_endpoints: RuntimeEndpoints) -> AsyncIterator[NativeUploadRuntime]:
    second_api = os.environ["UMBOD_TEST_API_B_BASE_URL"]
    second_mcp = os.environ["UMBOD_TEST_MCP_B_URL"]
    tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
    with httpx.Client(base_url=second_api, headers={
        "Authorization": "Bearer " + runtime_endpoints.bearer_token,
    }, timeout=30) as api, httpx.Client(base_url=runtime_endpoints.api_base_url, headers={
        "Authorization": "Bearer " + os.environ["UMBOD_TEST_BEARER_TOKEN_B"],
    }, timeout=30) as other_api, httpx.Client(
        base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30,
    ) as identity:
        policy_url = "/api/admin/filesystem/root-access"
        previous_response = api.get(policy_url)
        assert previous_response.status_code == 200
        previous = previous_response.json()
        configured = api.put(policy_url, json={
            "expected_revision": previous["revision"],
            "groups": [{"group_id": "admin", "permissions": ["discover", "write"]}],
        })
        assert configured.status_code == 200, configured.text
        try:
            root = checked_root_browse(api.get(FILESYSTEM + "/browse"))
            token = proxy_token(runtime_endpoints.mcp_url, runtime_endpoints.bearer_token, identity)
            other_token = proxy_token(second_mcp, os.environ["UMBOD_TEST_BEARER_TOKEN_B"], identity)
            async with mcp_client(runtime_endpoints.mcp_url, token) as client, mcp_client(second_mcp, other_token) as other_client:
                await wait_for_filesystem_tools(client, {"create_filesystem_directory", "filesystem_upload"})
                await wait_for_filesystem_tools(other_client, {"filesystem_upload"})
                directory = tool_payload(await client.call_tool("create_filesystem_directory", {
                    "parent_id": root["id"], "name": "native-upload-" + uuid4().hex,
                    "metadata": {"content_type": "application/octet-stream", "attributes": {}},
                }))
                yield NativeUploadRuntime(api, other_api, client, other_client, directory["id"])
        finally:
            current = api.get(policy_url)
            assert current.status_code == 200
            restored = api.put(policy_url, json={
                "expected_revision": current.json()["revision"], "groups": previous["groups"],
            })
            assert restored.status_code == 200, restored.text


@pytest.mark.asyncio
async def test_deployed_browser_and_mcp_advertise_the_same_configured_preview_limit(
    native_upload_runtime: NativeUploadRuntime, filesystem_preview_max_bytes: int,
) -> None:
    result = subprocess.run([
        "kubectl", "--context", os.environ["UMBOD_TEST_KUBE_CONTEXT"],
        "exec", "deployment/umbod-frontend", "--", "wget", "-qO-",
        "http://127.0.0.1:3000/app-config.json",
    ], check=True, capture_output=True, text=True, timeout=30)
    assert json.loads(result.stdout)["filesystemPreviewMaxBytes"] == filesystem_preview_max_bytes
    templates = await native_upload_runtime.client.list_resource_templates()
    template = next(item for item in templates if str(item.uri_template) == "umbod://filesystem/files/{node_id}")
    assert f"{filesystem_preview_max_bytes} bytes" in template.description


@pytest.mark.asyncio
@pytest.mark.parametrize("extra_bytes", [0, 1], ids=["at-configured-limit", "above-configured-limit"])
async def test_deployed_preview_limit_preserves_full_rest_downloads(
    native_upload_runtime: NativeUploadRuntime, filesystem_preview_max_bytes: int, extra_bytes: int,
) -> None:
    runtime = native_upload_runtime
    data = b"p" * (filesystem_preview_max_bytes + extra_bytes)
    uploaded = await runtime.client.call_tool("filesystem_upload", {
        "parent_id": runtime.directory_id, "name": "preview-boundary.txt",
        "metadata": {"content_type": "text/plain", "attributes": {}},
        "content": {"encoding": "utf-8", "text": data.decode("ascii")},
    })
    node = tool_payload(uploaded)
    uri = file_resource_link(uploaded, node["id"])
    downloaded = runtime.api.get(FILESYSTEM + "/nodes/" + node["id"] + "/content?delivery=stream")
    assert downloaded.status_code == 200
    assert downloaded.content == data
    await wait_for_filesystem_tools(runtime.client, {"filesystem_delete_file"})
    if extra_bytes:
        with pytest.raises(MCPError, match="filesystem_read_too_large"):
            await runtime.client.read_resource(uri)
    else:
        contents = await runtime.client.read_resource(uri)
        assert len(contents) == 1
        assert isinstance(contents[0], TextResourceContents)
        assert contents[0].text.encode("utf-8") == data


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


@pytest.mark.asyncio
@pytest.mark.parametrize("content,expected,content_type", [
    ({"encoding": "utf-8", "text": "résumé 東京\n"}, "résumé 東京\n".encode("utf-8"), "text/plain"),
    ({"encoding": "utf-8", "text": "{}"}, b"{}", "application/json"),
    ({"encoding": "utf-8", "text": "{}"}, b"{}", "application/vnd.umbod+json"),
    ({"encoding": "utf-8", "text": "<file/>"}, b"<file/>", "application/xml"),
    ({"encoding": "utf-8", "text": "<file/>"}, b"<file/>", "application/vnd.umbod+xml"),
    ({"encoding": "base64", "data": base64.b64encode(b"\x00\xff\x80\r\n").decode("ascii")}, b"\x00\xff\x80\r\n", "application/octet-stream"),
    ({"encoding": "utf-8", "text": "unknown"}, b"unknown", "application/x-unknown"),
    ({"encoding": "base64", "data": ""}, b"", "application/octet-stream"),
    ({"encoding": "base64", "data": base64.b64encode(PNG_BYTES).decode("ascii")}, PNG_BYTES, "image/png"),
    ({"encoding": "base64", "data": base64.b64encode(b"x" * 1_048_576).decode("ascii")}, b"x" * 1_048_576, "application/octet-stream"),
    ({"encoding": "base64", "data": base64.b64encode(b"x" * 10_485_760).decode("ascii")}, b"x" * 10_485_760, "application/octet-stream"),
], ids=["unicode-text", "json", "json-suffix", "xml", "xml-suffix", "binary", "unknown-mime", "empty", "png-image", "large-binary", "maximum-size"])
async def test_native_upload_is_readable_through_rest_and_private_across_workers(
    native_upload_runtime: NativeUploadRuntime, content: dict[str, str], expected: bytes, content_type: str,
    filesystem_preview_max_bytes: int,
) -> None:
    runtime = native_upload_runtime
    result = await runtime.client.call_tool("filesystem_upload", {
        "parent_id": runtime.directory_id, "name": "artifact.png" if content_type == "image/png" else "artifact.bin",
        "metadata": {"content_type": content_type, "attributes": {}},
        "content": content,
    })
    node = tool_payload(result)
    uri = file_resource_link(result, node["id"])
    assert node["parent_id"] == runtime.directory_id
    assert node["metadata"]["content_type"] == content_type
    path = FILESYSTEM + "/nodes/" + node["id"]
    assert checked_summary(runtime.api.get(path), 200) == node
    response = runtime.api.get(path + "/content?delivery=stream")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == content_type
    assert response.content == expected
    await wait_for_filesystem_tools(runtime.client, {"filesystem_delete_file"})
    if len(expected) <= filesystem_preview_max_bytes:
        contents = await runtime.client.read_resource(uri)
        assert len(contents) == 1
        resource = contents[0]
        assert str(resource.uri) == uri
        assert resource.mime_type == content_type
        assert resource.meta == {"revision": node["revision"], "size_bytes": len(expected)}
        if content_type.startswith("text/") or content_type in {"application/json", "application/xml"} or content_type.endswith(("+json", "+xml")):
            assert isinstance(resource, TextResourceContents)
            assert resource.text == expected.decode("utf-8")
        else:
            assert isinstance(resource, BlobResourceContents)
            assert base64.b64decode(resource.blob) == expected
    else:
        with pytest.raises(MCPError):
            await runtime.client.read_resource(uri)
    assert runtime.other_api.get(path).status_code == 403
    assert runtime.other_api.get(path + "/content").status_code == 403
    await wait_for_filesystem_tools(runtime.other_client, {"get_filesystem_node"})
    with pytest.raises(MCPError) as denied:
        await runtime.other_client.read_resource(uri)
    with pytest.raises(MCPError) as missing:
        await runtime.other_client.read_resource(file_resource_uri(str(uuid4())))
    assert denied.value.error.message == missing.value.error.message


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ["text/plain", "application/json", "application/xml", "application/vnd.umbod+json", "application/vnd.umbod+xml"])
async def test_known_text_resource_rejects_invalid_utf8_safely(
    native_upload_runtime: NativeUploadRuntime, content_type: str,
) -> None:
    runtime = native_upload_runtime
    data = b"private-invalid-text-\xff"
    result = await runtime.client.call_tool("filesystem_upload", {
        "parent_id": runtime.directory_id, "name": "invalid-text",
        "metadata": {"content_type": content_type, "attributes": {}},
        "content": {"encoding": "base64", "data": base64.b64encode(data).decode("ascii")},
    })
    node = tool_payload(result)
    await wait_for_filesystem_tools(runtime.client, {"filesystem_delete_file"})
    with pytest.raises(MCPError) as error:
        await runtime.client.read_resource(file_resource_link(result, node["id"]))
    assert "private-invalid-text" not in error.value.error.message
    assert "UnicodeDecodeError" not in error.value.error.message


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [
    {"encoding": "utf-8", "text": "é" * 5_242_881},
    {"encoding": "base64", "data": base64.b64encode(b"x" * 10_485_761).decode("ascii")},
], ids=["utf8-byte-limit", "base64-decoded-limit"])
async def test_native_oversize_upload_does_not_publish_a_file(
    native_upload_runtime: NativeUploadRuntime, content: dict[str, str],
) -> None:
    runtime = native_upload_runtime
    result = await runtime.client.call_tool("filesystem_upload", {
        "parent_id": runtime.directory_id, "name": "too-large.bin",
        "metadata": {"content_type": "application/octet-stream", "attributes": {}},
        "content": content,
    }, raise_on_error=False)
    assert result.is_error
    assert "filesystem_upload_too_large" in result.content[0].text
    children = tool_payload(await runtime.client.call_tool("list_filesystem_children", {
        "parent_id": runtime.directory_id,
    }))
    assert children["nodes"] == []


@pytest.mark.asyncio
async def test_read_rejects_oversize_rest_file_without_changing_rest_downloads(
    native_upload_runtime: NativeUploadRuntime, filesystem_preview_max_bytes: int,
) -> None:
    runtime = native_upload_runtime
    data = b"x" * (filesystem_preview_max_bytes + 1)
    begun = runtime.api.post(FILESYSTEM + "/nodes/" + runtime.directory_id + "/uploads", json={
        "name": "larger-rest-file.bin", "size_bytes": len(data),
        "metadata": {"content_type": "application/octet-stream", "attributes": {}},
    })
    assert begun.status_code == 201, "Upload begin failed"
    session = begun.json()
    assert_transfer_succeeded(transfer_upload(runtime.api, session["transfer"], data))
    node = checked_summary(runtime.api.post(session["complete_url"]), 201)
    await wait_for_filesystem_tools(runtime.client, {"filesystem_delete_file"})
    with pytest.raises(MCPError):
        await runtime.client.read_resource(file_resource_uri(node["id"]))
    downloaded = runtime.api.get(FILESYSTEM + "/nodes/" + node["id"] + "/content?delivery=stream")
    assert downloaded.status_code == 200
    assert downloaded.content == data


@pytest.mark.asyncio
async def test_native_upload_cannot_write_another_callers_directory(
    native_upload_runtime: NativeUploadRuntime,
) -> None:
    runtime = native_upload_runtime
    result = await runtime.other_client.call_tool("filesystem_upload", {
        "parent_id": runtime.directory_id, "name": "forbidden.txt",
        "metadata": {"content_type": "text/plain", "attributes": {}},
        "content": {"encoding": "utf-8", "text": "private"},
    }, raise_on_error=False)
    assert result.is_error
    assert "filesystem_permission_denied" in result.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    b"", b"\x00\xff\x80\r\n" * 1000, b"x" * 10_485_761,
], ids=["empty", "binary", "above-inline-limit"])
async def test_upload_session_transfers_original_bytes_without_oauth_credentials(
    native_upload_runtime: NativeUploadRuntime, runtime_endpoints: RuntimeEndpoints, data: bytes,
    filesystem_preview_max_bytes: int,
) -> None:
    runtime = native_upload_runtime
    await wait_for_filesystem_tools(runtime.client, {"filesystem_begin_upload", "filesystem_complete_upload"})
    digest = hashlib.sha256(data).hexdigest()
    begun = tool_payload(await runtime.client.call_tool("filesystem_begin_upload", {
        "parent_id": runtime.directory_id, "name": "original.bin", "size_bytes": len(data),
        "expected_sha256": digest,
        "metadata": {"content_type": "application/octet-stream", "attributes": {}},
    }))
    transfer = begun["transfer"]
    assert begun["complete_tool"] == "filesystem_complete_upload"
    assert transfer["method"] == "PUT"
    if s3_runtime():
        assert_s3_transfer(transfer)
    else:
        assert transfer["url"].startswith(runtime_endpoints.api_base_url + "/api/filesystem/uploads/")
    assert "Authorization" not in transfer["headers"]
    with httpx.Client(timeout=60, follow_redirects=False) as anonymous:
        assert_transfer_succeeded(transfer_upload(anonymous, transfer, data))
    completed = await runtime.client.call_tool("filesystem_complete_upload", {"upload_id": begun["upload_id"]})
    receipt = tool_payload(completed)
    node = receipt["node"]
    uri = file_resource_link(completed, node["id"])
    assert receipt["size_bytes"] == len(data)
    assert receipt["sha256"] == digest
    assert node["parent_id"] == runtime.directory_id
    downloaded = runtime.api.get(FILESYSTEM + "/nodes/" + node["id"] + "/content?delivery=stream")
    assert downloaded.status_code == 200
    assert downloaded.content == data
    repeated = tool_payload(await runtime.client.call_tool("filesystem_complete_upload", {"upload_id": begun["upload_id"]}))
    assert repeated == receipt
    assert runtime.other_api.get(FILESYSTEM + "/nodes/" + node["id"]).status_code == 403
    if len(data) <= filesystem_preview_max_bytes:
        resources = await runtime.client.read_resource(uri)
        assert len(resources) == 1
        assert isinstance(resources[0], BlobResourceContents)
        assert base64.b64decode(resources[0].blob) == data


@pytest.mark.asyncio
@pytest.mark.skipif(s3_runtime(), reason="API transfer capabilities apply only to local storage")
async def test_upload_transfer_capability_does_not_authorize_other_operations_or_replay(
    native_upload_runtime: NativeUploadRuntime,
) -> None:
    runtime = native_upload_runtime
    await wait_for_filesystem_tools(runtime.client, {"filesystem_begin_upload", "filesystem_complete_upload"})
    begun = tool_payload(await runtime.client.call_tool("filesystem_begin_upload", {
        "parent_id": runtime.directory_id, "name": "capability.bin", "size_bytes": 3,
        "metadata": {"content_type": "application/octet-stream", "attributes": {}},
    }))
    transfer = begun["transfer"]
    with httpx.Client(timeout=30, follow_redirects=False) as anonymous:
        denied = anonymous.put(transfer["url"], content=b"abc", headers={"Content-Type": "application/octet-stream"})
        assert denied.status_code == 403
        wrong = anonymous.put(transfer["url"], content=b"abc", headers={
            **transfer["headers"], "X-Umbod-Upload-Token": "incorrect-token",
        })
        assert wrong.status_code == 403
        assert wrong.json() == denied.json()
        assert anonymous.get(transfer["url"], headers=transfer["headers"]).status_code == 401
        session_url = transfer["url"].removesuffix("/transfer")
        assert anonymous.get(session_url, headers=transfer["headers"]).status_code == 401
        assert anonymous.post(session_url + "/complete", headers=transfer["headers"]).status_code == 401
        assert anonymous.put(transfer["url"], content=b"abc", headers=transfer["headers"]).status_code == 204
        assert anonymous.put(transfer["url"], content=b"xyz", headers=transfer["headers"]).status_code == 409
    await wait_for_filesystem_tools(runtime.other_client, {"filesystem_complete_upload"})
    denied_completion = await runtime.other_client.call_tool("filesystem_complete_upload", {
        "upload_id": begun["upload_id"],
    }, raise_on_error=False)
    assert denied_completion.is_error
    assert "filesystem_permission_denied" in denied_completion.content[0].text
    receipt = tool_payload(await runtime.client.call_tool("filesystem_complete_upload", {"upload_id": begun["upload_id"]}))
    assert receipt["sha256"] == hashlib.sha256(b"abc").hexdigest()


@pytest.mark.asyncio
@pytest.mark.skipif(s3_runtime(), reason="Local streaming transfer rejects mismatches before completion")
async def test_upload_checksum_mismatch_can_retry_without_publishing_bad_content(
    native_upload_runtime: NativeUploadRuntime,
) -> None:
    runtime = native_upload_runtime
    await wait_for_filesystem_tools(runtime.client, {"filesystem_begin_upload", "filesystem_complete_upload"})
    begun = tool_payload(await runtime.client.call_tool("filesystem_begin_upload", {
        "parent_id": runtime.directory_id, "name": "verified.bin", "size_bytes": 3,
        "expected_sha256": hashlib.sha256(b"abc").hexdigest(),
        "metadata": {"content_type": "application/octet-stream", "attributes": {}},
    }))
    transfer = begun["transfer"]
    with httpx.Client(timeout=30, follow_redirects=False) as anonymous:
        mismatch = anonymous.put(transfer["url"], content=b"xyz", headers=transfer["headers"])
        assert mismatch.status_code == 422
        pending = await runtime.client.call_tool("filesystem_complete_upload", {
            "upload_id": begun["upload_id"],
        }, raise_on_error=False)
        assert pending.is_error
        children = tool_payload(await runtime.client.call_tool("list_filesystem_children", {
            "parent_id": runtime.directory_id,
        }))
        assert children["nodes"] == []
        assert anonymous.put(transfer["url"], content=b"abc", headers=transfer["headers"]).status_code == 204
    receipt = tool_payload(await runtime.client.call_tool("filesystem_complete_upload", {"upload_id": begun["upload_id"]}))
    assert receipt["sha256"] == hashlib.sha256(b"abc").hexdigest()


@pytest.mark.asyncio
async def test_write_errors_explain_recovery_and_include_server_identity(
    native_upload_runtime: NativeUploadRuntime,
) -> None:
    runtime = native_upload_runtime
    arguments = {
        "parent_id": runtime.directory_id,
        "name": "diagnostic-file",
        "metadata": {"content_type": "text/plain", "attributes": {}},
        "content": {"encoding": "utf-8", "text": "private-content-sentinel"},
    }
    created = await runtime.client.call_tool("filesystem_upload", arguments)
    denied = await runtime.other_client.call_tool("filesystem_upload", arguments, raise_on_error=False)
    node = tool_payload(created)
    response = runtime.api.get(FILESYSTEM + "/nodes/" + node["id"])
    assert response.status_code == 200
    success_metadata = created.meta["computerlove.tech/umbod"]
    failure_metadata = denied.meta["computerlove.tech/umbod"]
    assert success_metadata["server_version"] == response.headers["X-Umbod-Version"]
    assert failure_metadata["server_version"] == success_metadata["server_version"]
    assert failure_metadata["server_revision"] == response.headers["X-Umbod-Revision"]
    assert success_metadata["schema_version"] == failure_metadata["schema_version"] == 1
    assert success_metadata["guidance"]["outcome"] == "success"
    assert success_metadata["guidance"]["operation_state"] == "completed"
    assert success_metadata["guidance"]["recovery"]["retry"] == "not_needed"
    assert success_metadata["guidance"]["error"] is None
    assert success_metadata["guidance"]["recovery"]["instructions"] == []
    assert success_metadata["guidance"]["notices"] == []
    assert success_metadata["guidance"]["extensions"] == {}
    assert success_metadata["extensions"] == {}
    assert failure_metadata["guidance"]["outcome"] == "failure"
    assert failure_metadata["guidance"]["operation_state"] == "unknown"
    assert failure_metadata["guidance"]["recovery"]["retry"] == "inspect_before_retry"
    assert failure_metadata["guidance"]["error"]["code"] == "filesystem_permission_denied"
    assert denied.is_error
    assert "discover and write on the parent directory" in denied.content[1].text
    assert "filesystem_browse operation home" in denied.content[1].text
    assert failure_metadata["request_id"] != success_metadata["request_id"]
    assert failure_metadata["request_id"] in denied.content[-1].text
    guidance = failure_metadata["guidance"]
    assert guidance["recovery"]["instructions"]
    for instruction in guidance["recovery"]["instructions"]:
        assert instruction in denied.content[1].text
    for value in (guidance["outcome"], guidance["operation_state"], guidance["recovery"]["retry"]):
        assert value in denied.content[1].text
    assert "private-content-sentinel" not in " ".join(block.text for block in denied.content)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,patch,field", [
    ("filesystem_browse", {"operation": "stat", "target": {"type": "path", "path": "SECRET_PATH"}}, "target.path"),
    ("update_filesystem_node", {
        "expected_revision": 1, "metadata": {"attributes": {"SECRET_KEY": {"nested": "SECRET_VALUE"}}},
    }, "metadata.attributes"),
    ("filesystem_begin_upload", {
        "name": "private", "metadata": {"content_type": {}, "attributes": {}},
        "size_bytes": 0, "expected_sha256": "SECRET_HASH",
    }, "expected_sha256"),
    ("create_filesystem_file", {
        "name": "private", "metadata": {"content_type": {}, "attributes": {"SECRET_KEY": {"nested": "SECRET_VALUE"}}},
    }, "metadata.attributes"),
])
async def test_argument_errors_identify_fields_without_echoing_values(
    native_upload_runtime: NativeUploadRuntime, tool: str, patch: dict[str, object], field: str,
) -> None:
    runtime = native_upload_runtime
    await wait_for_filesystem_tools(runtime.client, {tool})
    identifiers = {
        "filesystem_browse": {},
        "update_filesystem_node": {"node_id": runtime.directory_id},
        "filesystem_begin_upload": {"parent_id": runtime.directory_id},
        "create_filesystem_file": {"parent_id": runtime.directory_id},
    }[tool]
    result = await runtime.client.call_tool(tool, {**identifiers, **patch}, raise_on_error=False)
    assert result.is_error
    assert field in result.content[0].text
    metadata = result.meta["computerlove.tech/umbod"]
    assert metadata["schema_version"] == 1
    assert metadata["guidance"]["outcome"] == "failure"
    assert metadata["guidance"]["operation_state"] == "not_started"
    assert metadata["guidance"]["recovery"]["retry"] == "after_correction"
    assert field in {issue["field"] for issue in metadata["guidance"]["error"]["issues"]}
    assert metadata["guidance"]["recovery"]["instructions"]
    for issue in metadata["guidance"]["error"]["issues"]:
        assert issue["field"] in result.content[0].text
        assert issue["correction"] in result.content[0].text
    for instruction in metadata["guidance"]["recovery"]["instructions"]:
        assert instruction in result.content[1].text
    assert "SECRET" not in repr(result)
    assert result.meta["computerlove.tech/umbod"]["request_id"] in result.content[-1].text
    children = tool_payload(await runtime.client.call_tool("list_filesystem_children", {
        "parent_id": runtime.directory_id,
    }))
    assert children["nodes"] == []
