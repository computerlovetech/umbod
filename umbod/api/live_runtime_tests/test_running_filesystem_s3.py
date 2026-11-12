import base64
import hashlib
import json
import os
import ssl
import subprocess
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx
import pytest
from mcp.types import BlobResourceContents

from conftest import RuntimeEndpoints
from test_running_filesystem import FILESYSTEM, checked_summary, file_resource_uri, tool_payload, wait_for_filesystem_tools
from test_running_filesystem_uploads import NativeUploadRuntime, native_upload_runtime as native_upload_runtime
from test_running_personal_mcp_execution import mcp_client, proxy_token
from upload_transfer_support import assert_s3_transfer, assert_transfer_succeeded, raw_s3_request, transfer_upload


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.environ.get("UMBOD_TEST_CONTENT_BACKEND") != "s3", reason="S3 Kind mode only"),
]


def storage_objects() -> dict[str, dict[str, Any]]:
    result = subprocess.run([
        "kubectl", "--context", os.environ["UMBOD_TEST_KUBE_CONTEXT"],
        "exec", "deployment/umbod-core", "-c", "api", "--", "python",
        "/s3-fixture/setup_s3_runtime.py", "inspect",
    ], capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, "In-cluster S3 inspection failed"
    return {item["key"]: item for item in json.loads(result.stdout)}


def upload_request(runtime: NativeUploadRuntime, name: str, size: int) -> dict[str, Any]:
    response = runtime.api.post(FILESYSTEM + "/nodes/" + runtime.directory_id + "/uploads", json={
        "name": name, "size_bytes": size,
        "metadata": {"content_type": "application/octet-stream", "attributes": {}},
    })
    assert response.status_code == 201, "Upload begin failed"
    session = response.json()
    assert session["transfer"]["authorization"] == {"type": "none"}
    assert_s3_transfer(session["transfer"])
    return session


def children(runtime: NativeUploadRuntime) -> list[dict[str, Any]]:
    response = runtime.api.get(FILESYSTEM + "/nodes/" + runtime.directory_id + "/children")
    assert response.status_code == 200, response.text
    return response.json()["nodes"]


@pytest.mark.parametrize("content", [b"", b"\x00\xff\x80\r\n", bytes(range(256)) * 36864], ids=["empty", "binary", "single-put-9mib"])
async def test_s3_direct_put_publishes_only_after_completion_and_survives_worker_reopen(
    native_upload_runtime: NativeUploadRuntime, runtime_endpoints: RuntimeEndpoints, content: bytes,
    filesystem_preview_max_bytes: int,
) -> None:
    runtime = native_upload_runtime
    before = storage_objects()
    session = upload_request(runtime, "immutable.bin", len(content))
    assert children(runtime) == []
    transferred = transfer_upload(runtime.api, session["transfer"], content)
    assert_transfer_succeeded(transferred)
    assert children(runtime) == []
    staged = storage_objects()
    added = staged.keys() - before.keys()
    assert len(added) == 1
    key = added.pop()
    assert all(object_key.startswith("runtime/") for object_key in staged)
    assert key.startswith("runtime/")
    assert "umbod-runtime-content" not in key
    assert "://" not in key
    assert staged[key]["size"] == len(content)
    assert staged[key]["etag"] == transferred.headers["etag"]
    assert "-" not in staged[key]["etag"]
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers={
        "Authorization": "Bearer " + runtime_endpoints.bearer_token,
    }, timeout=60) as primary:
        completed = primary.post(session["complete_url"])
        node = checked_summary(completed, 201)
        assert key not in completed.text
        assert "umbod-runtime-content" not in completed.text
        path = FILESYSTEM + "/nodes/" + node["id"]
        downloaded = primary.get(path + "/content?delivery=stream")
        assert downloaded.status_code == 200
        assert downloaded.content == content
    reopened = runtime.api.get(path + "/content?delivery=stream")
    assert reopened.status_code == 200
    assert reopened.content == content
    if len(content) <= filesystem_preview_max_bytes:
        await wait_for_filesystem_tools(runtime.client, {"filesystem_delete_file"})
        uri = file_resource_uri(node["id"])
        read = await runtime.client.read_resource(uri)
        assert len(read) == 1
        assert isinstance(read[0], BlobResourceContents)
        assert base64.b64decode(read[0].blob) == content
        assert read[0].meta == {"revision": node["revision"], "size_bytes": len(content)}
        tls = ssl.create_default_context(cafile=os.environ["UMBOD_TEST_PERSONAL_CA"])
        with httpx.Client(base_url=os.environ["UMBOD_TEST_PERSONAL_URL"], verify=tls, timeout=30) as identity:
            endpoint = os.environ["UMBOD_TEST_MCP_B_URL"]
            token = proxy_token(endpoint, runtime_endpoints.bearer_token, identity)
            async with mcp_client(endpoint, token) as secondary:
                await wait_for_filesystem_tools(secondary, {"filesystem_delete_file"})
                secondary_read = await secondary.read_resource(uri)
                assert secondary_read == read
    assert storage_objects()[key] == staged[key]
    late = transfer_upload(runtime.api, session["transfer"], content)
    assert late.status_code == 412
    assert storage_objects()[key] == staged[key]
    assert runtime.api.get(path + "/content?delivery=stream").content == content


async def test_s3_content_redirect_is_private_get_only_and_preserves_stream_and_mcp_reads(
    native_upload_runtime: NativeUploadRuntime,
) -> None:
    runtime = native_upload_runtime
    content = bytes(range(256)) * 32 + b"\x00\xffdirect S3 download\r\n"
    filename = "download.bin"
    disposition = "attachment; filename=\"download\"; filename*=UTF-8''download.bin"
    session = upload_request(runtime, filename, len(content))
    assert_transfer_succeeded(transfer_upload(runtime.api, session["transfer"], content))
    node = checked_summary(runtime.api.post(session["complete_url"]), 201)
    path = FILESYSTEM + "/nodes/" + node["id"] + "/content"

    redirected = runtime.api.get(path, follow_redirects=False)
    assert redirected.status_code == 307
    assert redirected.headers["cache-control"] == "no-store"
    assert redirected.headers["referrer-policy"] == "no-referrer"
    location = redirected.headers["location"]
    parsed = urlsplit(location)
    assert parsed.scheme == "http"
    assert parsed.netloc == "umbod-runtime-s3:5000"
    query = parse_qs(parsed.query)
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["X-Amz-Expires"] == ["300"]
    assert query["X-Amz-Signature"]
    assert query["X-Amz-SignedHeaders"] == ["host"]
    assert query["response-content-type"] == ["application/octet-stream"]
    assert query["response-content-disposition"] == [disposition]
    assert query["response-cache-control"] == ["no-store"]

    transfer = {"url": location, "headers": {}}
    downloaded = raw_s3_request(transfer, b"", method="GET")
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["content-type"] == "application/octet-stream"
    assert downloaded.headers["content-disposition"] == disposition
    assert downloaded.headers["cache-control"] == "no-store"
    assert raw_s3_request(transfer, b"", method="PUT").status_code == 403
    unsigned = {"url": urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")), "headers": {}}
    assert raw_s3_request(unsigned, b"", method="GET").status_code == 403
    denied = runtime.other_api.get(path, follow_redirects=False)
    assert denied.status_code == 403
    assert "location" not in denied.headers

    streamed = runtime.api.get(path, params={"delivery": "stream"}, follow_redirects=False)
    assert streamed.status_code == 200
    assert streamed.content == content
    assert "location" not in streamed.headers
    await wait_for_filesystem_tools(runtime.client, {"filesystem_delete_file"})
    resources = await runtime.client.read_resource(file_resource_uri(node["id"]))
    assert len(resources) == 1
    assert isinstance(resources[0], BlobResourceContents)
    assert base64.b64decode(resources[0].blob) == content
    assert resources[0].mime_type == "application/octet-stream"
    assert resources[0].meta == {"revision": node["revision"], "size_bytes": len(content)}


async def test_s3_pending_transfer_cannot_complete_or_publish(
    native_upload_runtime: NativeUploadRuntime,
) -> None:
    runtime = native_upload_runtime
    before = storage_objects()
    pending = upload_request(runtime, "pending.bin", 5)
    assert runtime.api.post(pending["complete_url"]).status_code == 409
    assert children(runtime) == []
    assert storage_objects() == before


async def test_s3_direct_put_is_private_and_cannot_overwrite_or_authorize_completion(
    native_upload_runtime: NativeUploadRuntime,
) -> None:
    runtime = native_upload_runtime
    session = upload_request(runtime, "private.bin", 3)
    transfer = session["transfer"]
    assert_transfer_succeeded(transfer_upload(runtime.api, transfer, b"abc"))
    parsed = urlsplit(transfer["url"])
    unsigned = {"url": urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")), "headers": {}}
    assert raw_s3_request(unsigned, b"", method="GET").status_code == 403
    assert raw_s3_request(transfer, b"xyz").status_code == 412
    assert children(runtime) == []
    assert runtime.other_api.post(session["complete_url"]).status_code == 403
    with httpx.Client(base_url=str(runtime.api.base_url), timeout=30, follow_redirects=False) as anonymous:
        assert anonymous.post(session["complete_url"]).status_code == 401
    await wait_for_filesystem_tools(runtime.other_client, {"filesystem_complete_upload"})
    denied = await runtime.other_client.call_tool("filesystem_complete_upload", {
        "upload_id": session["id"],
    }, raise_on_error=False)
    assert denied.is_error
    assert "filesystem_permission_denied" in denied.content[0].text
    await wait_for_filesystem_tools(runtime.client, {"filesystem_complete_upload"})
    receipt = tool_payload(await runtime.client.call_tool("filesystem_complete_upload", {
        "upload_id": session["id"],
    }))
    assert receipt["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert receipt["size_bytes"] == 3
    path = FILESYSTEM + "/nodes/" + receipt["node"]["id"]
    assert runtime.api.get(path + "/content?delivery=stream").content == b"abc"
    assert runtime.other_api.get(path + "/content").status_code == 403
    assert raw_s3_request(transfer, b"xyz").status_code == 412
    assert runtime.api.get(path + "/content?delivery=stream").content == b"abc"


@pytest.mark.parametrize("completion", ["rest", "mcp"])
async def test_s3_completion_verifies_stored_bytes_before_publication(
    native_upload_runtime: NativeUploadRuntime, completion: str,
) -> None:
    runtime = native_upload_runtime
    await wait_for_filesystem_tools(runtime.client, {"filesystem_begin_upload", "filesystem_complete_upload"})
    begun = tool_payload(await runtime.client.call_tool("filesystem_begin_upload", {
        "parent_id": runtime.directory_id, "name": "checksum.bin", "size_bytes": 3,
        "expected_sha256": hashlib.sha256(b"abc").hexdigest(),
        "metadata": {"content_type": "application/octet-stream", "attributes": {}},
    }))
    assert_transfer_succeeded(transfer_upload(runtime.api, begun["transfer"], b"xyz"))
    assert children(runtime) == []
    if completion == "rest":
        rejected = runtime.api.post(FILESYSTEM + "/uploads/" + begun["upload_id"] + "/complete")
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == "filesystem_upload_checksum_mismatch"
    else:
        result = await runtime.client.call_tool("filesystem_complete_upload", {
            "upload_id": begun["upload_id"],
        }, raise_on_error=False)
        assert result.is_error
        assert "filesystem_upload_checksum_mismatch" in result.content[0].text
    assert children(runtime) == []
