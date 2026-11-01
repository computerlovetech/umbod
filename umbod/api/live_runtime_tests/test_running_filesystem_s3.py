import base64
from collections.abc import Iterator
import json
import os
import ssl
import subprocess
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
from mcp.types import BlobResourceContents

from conftest import RuntimeEndpoints
from test_running_filesystem import FILESYSTEM, checked_summary, file_resource_uri, wait_for_filesystem_tools
from test_running_filesystem_uploads import NativeUploadRuntime, native_upload_runtime as native_upload_runtime
from test_running_personal_mcp_execution import mcp_client, proxy_token


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.environ.get("UMBOD_TEST_CONTENT_BACKEND") != "s3", reason="S3 Kind mode only"),
]


def storage_objects() -> dict[str, dict[str, Any]]:
    result = subprocess.run([
        "kubectl", "--context", os.environ["UMBOD_TEST_KUBE_CONTEXT"],
        "exec", "deployment/umbod-core", "-c", "api", "--", "python",
        "/s3-fixture/setup_s3_runtime.py", "inspect",
    ], capture_output=True, text=True, check=True)
    return {item["key"]: item for item in json.loads(result.stdout)}


def upload_request(runtime: NativeUploadRuntime, name: str, size: int) -> dict[str, Any]:
    response = runtime.api.post(FILESYSTEM + "/nodes/" + runtime.directory_id + "/uploads", json={
        "name": name, "size_bytes": size,
        "metadata": {"content_type": "application/octet-stream", "attributes": {}},
    })
    assert response.status_code == 201, response.text
    session = response.json()
    assert session["transfer"]["type"] == "single"
    assert session["transfer"]["authorization"] == {"type": "same_origin"}
    assert urlsplit(session["transfer"]["url"]).netloc in ("", urlsplit(str(runtime.api.base_url)).netloc)
    assert "umbod-runtime-content" not in response.text
    assert "umbod-runtime-s3" not in response.text
    assert ":5000" not in response.text
    return session


def content_chunks(content: bytes) -> Iterator[bytes]:
    for offset in range(0, len(content), 65536):
        yield content[offset:offset + 65536]


def children(runtime: NativeUploadRuntime) -> list[dict[str, Any]]:
    response = runtime.api.get(FILESYSTEM + "/nodes/" + runtime.directory_id + "/children")
    assert response.status_code == 200, response.text
    return response.json()["nodes"]


@pytest.mark.parametrize("content", [b"", b"\x00\xff\x80\r\n", bytes(range(256)) * 36864], ids=["empty", "binary", "multipart-9mib"])
async def test_s3_stream_upload_publishes_only_after_completion_and_survives_worker_reopen(
    native_upload_runtime: NativeUploadRuntime, runtime_endpoints: RuntimeEndpoints, content: bytes,
) -> None:
    runtime = native_upload_runtime
    before = storage_objects()
    session = upload_request(runtime, "immutable.bin", len(content))
    assert children(runtime) == []
    transferred = runtime.api.put(session["transfer"]["url"], content=content_chunks(content), headers=session["transfer"]["headers"])
    assert transferred.status_code == 204, transferred.text
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
    if len(content) > 8 * 1024 * 1024:
        assert staged[key]["etag"].endswith('-2"')
    with httpx.Client(base_url=runtime_endpoints.api_base_url, headers={
        "Authorization": "Bearer " + runtime_endpoints.bearer_token,
    }, timeout=60) as primary:
        completed = primary.post(session["complete_url"])
        node = checked_summary(completed, 201)
        assert key not in completed.text
        assert "umbod-runtime-content" not in completed.text
        path = FILESYSTEM + "/nodes/" + node["id"]
        downloaded = primary.get(path + "/content")
        assert downloaded.status_code == 200
        assert downloaded.content == content
    reopened = runtime.api.get(path + "/content")
    assert reopened.status_code == 200
    assert reopened.content == content
    if len(content) <= 1_048_576:
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
    late = runtime.api.put(session["transfer"]["url"], content=b"replacement", headers=session["transfer"]["headers"])
    assert late.status_code == 409
    assert storage_objects()[key] == staged[key]
    assert runtime.api.get(path + "/content").content == content


async def test_s3_pending_and_rejected_transfers_publish_no_nodes(
    native_upload_runtime: NativeUploadRuntime,
) -> None:
    runtime = native_upload_runtime
    before = storage_objects()
    pending = upload_request(runtime, "pending.bin", 5)
    assert runtime.api.post(pending["complete_url"]).status_code == 409
    failed = upload_request(runtime, "short.bin", 5)
    response = runtime.api.put(failed["transfer"]["url"], content=content_chunks(b"bad"), headers=failed["transfer"]["headers"])
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "filesystem_upload_length_mismatch"
    assert runtime.api.post(failed["complete_url"]).status_code == 409
    assert children(runtime) == []
    assert storage_objects() == before
