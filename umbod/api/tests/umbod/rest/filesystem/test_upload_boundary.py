from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import Request

from umbod.rest.authentication.deps import get_caller_context

from .conftest import FilesystemHttp
from .test_content import begin_upload
from .test_http_contract import BASE


@pytest.mark.parametrize("reason", ["foreign", "unknown", "revoked", "media_type", "completed"])
def test_raw_transfer_rejects_before_consuming_request_stream(
    filesystem_http: FilesystemHttp, monkeypatch: pytest.MonkeyPatch, reason: str,
) -> None:
    client = filesystem_http.client
    from .conftest import create_shared_namespace, replace_shared_access

    namespace = create_shared_namespace(filesystem_http, "read_write")
    session = begin_upload(client, f"{BASE}/nodes/{namespace.root_node_id}/uploads", "file", b"x").json()
    headers = session["transfer"]["headers"]
    path = session["transfer"]["url"]
    expected = 403
    if reason == "foreign":
        headers = {**headers, "Authorization": "Bearer bob"}
    elif reason == "unknown":
        path = f"{BASE}/uploads/{uuid4()}/content"
    elif reason == "revoked":
        replace_shared_access(filesystem_http, namespace, "read")
    elif reason == "media_type":
        headers = {"Content-Type": "text/plain"}
        expected = 415
    else:
        assert client.put(path, content=b"x", headers=headers).status_code == 204
        assert client.post(session["complete_url"]).status_code == 201
        expected = 409

    async def forbid_stream(self: Request) -> AsyncIterator[bytes]:
        pytest.fail("Unauthorized upload stream was consumed")
        yield b""

    monkeypatch.setattr(Request, "stream", forbid_stream)
    assert client.put(path, content=b"x", headers=headers).status_code == expected


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("PUT", "/content"), ("POST", "/complete")])
def test_session_paths_require_authentication_and_verified_identity(
    filesystem_http: FilesystemHttp, method: str, suffix: str,
) -> None:
    path = f"{BASE}/uploads/{uuid4()}{suffix}"
    assert filesystem_http.client.request(method, path, headers={"Authorization": ""}).status_code == 401
    del filesystem_http.app.dependency_overrides[get_caller_context]
    assert filesystem_http.client.request(method, path).status_code == 403


def test_removed_upload_routes_are_absent_from_openapi(filesystem_http: FilesystemHttp) -> None:
    client = filesystem_http.client
    paths = client.get("/api/me/openapi.json").json()["paths"]
    assert "/filesystem/nodes/{parent_id}/files" not in paths
    assert "/filesystem/nodes/{parent_id}/upload-policy" not in paths
    for method, suffix in [("post", "files"), ("get", "upload-policy")]:
        assert client.request(method, f"{BASE}/nodes/{uuid4()}/{suffix}").status_code == 404
    begin = paths["/filesystem/nodes/{parent_id}/uploads"]
    assert set(begin) == {"post"}
    transfer = paths["/filesystem/uploads/{upload_id}/content"]["put"]
    assert set(transfer["requestBody"]["content"]) == {"application/octet-stream"}
    complete = paths["/filesystem/uploads/{upload_id}/complete"]["post"]
    assert "requestBody" not in complete
    assert {"200", "201"} <= set(complete["responses"])
    assert "get" in paths["/filesystem/uploads/{upload_id}"]
