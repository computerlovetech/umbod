import base64
import os
import ssl
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
    FILESYSTEM, checked_summary, file_resource_link, file_resource_uri, tool_payload, wait_for_filesystem_tools,
)
from test_running_personal_mcp_execution import mcp_client, proxy_token


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
            root = checked_summary(api.get(FILESYSTEM + "/root"), 200)
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
], ids=["unicode-text", "json", "json-suffix", "xml", "xml-suffix", "binary", "unknown-mime", "empty", "png-image", "resource-limit", "maximum-size"])
async def test_native_upload_is_readable_through_rest_and_private_across_workers(
    native_upload_runtime: NativeUploadRuntime, content: dict[str, str], expected: bytes, content_type: str,
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
    response = runtime.api.get(path + "/content")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == content_type
    assert response.content == expected
    await wait_for_filesystem_tools(runtime.client, {"filesystem_delete_file"})
    if len(expected) <= 1_048_576:
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
    native_upload_runtime: NativeUploadRuntime,
) -> None:
    runtime = native_upload_runtime
    data = b"x" * 1_048_577
    begun = runtime.api.post(FILESYSTEM + "/nodes/" + runtime.directory_id + "/uploads", json={
        "name": "larger-rest-file.bin", "size_bytes": len(data),
        "metadata": {"content_type": "application/octet-stream", "attributes": {}},
    })
    assert begun.status_code == 201, begun.text
    session = begun.json()
    transferred = runtime.api.put(
        session["transfer"]["url"], content=data, headers=session["transfer"]["headers"],
    )
    assert transferred.status_code == 204, transferred.text
    node = checked_summary(runtime.api.post(session["complete_url"]), 201)
    await wait_for_filesystem_tools(runtime.client, {"filesystem_delete_file"})
    with pytest.raises(MCPError):
        await runtime.client.read_resource(file_resource_uri(node["id"]))
    downloaded = runtime.api.get(FILESYSTEM + "/nodes/" + node["id"] + "/content")
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
