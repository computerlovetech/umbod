import json
from collections.abc import Iterator
from urllib.parse import quote
from uuid import uuid4

import pytest

from umbod.core.filesystem import ByteStream, ContentRef, StorageKey
from umbod.infrastructure import InMemoryContentConfig, create_content_driver
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.filesystem.deps import get_filesystem_content_driver

from .conftest import FilesystemHttp
from .test_http_contract import BASE, BODY, creation_payload

MultipartPart = tuple[str, tuple[str, bytes, str] | tuple[None, str]]


@pytest.fixture
def upload_path(filesystem_http: FilesystemHttp) -> str:
    root_id = filesystem_http.client.get(f"{BASE}/root").json()["id"]
    return f"{BASE}/nodes/{root_id}/files"


def content_path(identifier: str) -> str:
    return f"{BASE}/nodes/{identifier}/content"


def multipart_chunks(payload: bytes) -> Iterator[bytes]:
    prefix = (
        b"--upload\r\nContent-Disposition: form-data; name=\"file\"; "
        b"filename=\"chunked.bin\"\r\nContent-Type: application/octet-stream\r\n\r\n"
    )
    yield prefix
    for offset in range(0, len(payload), 3):
        yield payload[offset:offset + 3]
    yield b"\r\n--upload--\r\n"


@pytest.mark.parametrize("payload", [b"\x00\xff\x80binary\r\n\x00", b""])
def test_upload_download_preserves_binary_bytes_and_safe_headers(
    filesystem_http: FilesystemHttp, upload_path: str, payload: bytes,
) -> None:
    uploaded = filesystem_http.client.post(upload_path, files={
        "file": ("payload.bin", payload, "application/octet-stream"),
    })
    assert uploaded.status_code == 201
    node = uploaded.json()
    assert node["name"] == "payload.bin"
    assert node["metadata"] == {"content_type": "application/octet-stream", "attributes": {}}
    assert uploaded.headers["cache-control"] == "no-store"
    assert set(node) == {"id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision"}
    downloaded = filesystem_http.client.get(content_path(node["id"]))
    assert downloaded.status_code == 200
    assert downloaded.content == payload
    assert downloaded.headers["content-type"] == "application/octet-stream"
    assert downloaded.headers["cache-control"] == "no-store"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert "payload.bin" in downloaded.headers["content-disposition"]


def test_unicode_upload_name_has_utf8_attachment_filename(
    filesystem_http: FilesystemHttp, upload_path: str,
) -> None:
    filename = 'résumé-東京-"notes".bin'
    uploaded = filesystem_http.client.post(upload_path, files={
        "file": ("original.bin", b"unicode", "application/octet-stream"),
    }, data={"name": filename})
    assert uploaded.status_code == 201
    assert uploaded.json()["name"] == filename
    downloaded = filesystem_http.client.get(content_path(uploaded.json()["id"]))
    assert downloaded.status_code == 200
    disposition = downloaded.headers["content-disposition"]
    assert "filename*=UTF-8''" + quote(filename, safe="") in disposition
    assert "\r" not in disposition and "\n" not in disposition
    assert downloaded.content == b"unicode"


@pytest.mark.parametrize("metadata", [
    {"content_type": "application/custom", "attributes": {"label": "overridden"}},
    {"content_type": {}, "attributes": {}},
])
def test_explicit_metadata_overrides_uploaded_part_content_type(
    filesystem_http: FilesystemHttp, upload_path: str, metadata: dict[str, object],
) -> None:
    uploaded = filesystem_http.client.post(upload_path, files={
        "file": ("original.txt", b"payload", "text/plain"),
    }, data={"name": "renamed.txt", "metadata": json.dumps(metadata)})
    assert uploaded.status_code == 201
    assert uploaded.json()["name"] == "renamed.txt"
    assert uploaded.json()["metadata"] == metadata
    downloaded = filesystem_http.client.get(content_path(uploaded.json()["id"]))
    assert downloaded.status_code == 200
    assert downloaded.content == b"payload"


@pytest.mark.parametrize("metadata", [
    "not-json", "null", "[]", "{}",
    '{"content_type":12,"attributes":{}}',
    '{"content_type":{"invalid":true},"attributes":{}}',
    '{"content_type":"text/plain","attributes":[]}',
    '{"content_type":"text/plain","attributes":{},"owner":"mallory"}',
])
def test_upload_rejects_invalid_metadata_without_creating_node(
    filesystem_http: FilesystemHttp, upload_path: str, metadata: str,
) -> None:
    response = filesystem_http.client.post(upload_path, files={
        "file": ("invalid.bin", b"payload", "application/octet-stream"),
    }, data={"metadata": metadata})
    assert response.status_code == 422
    children = filesystem_http.client.get(upload_path.removesuffix("/files") + "/children")
    assert children.json() == {"nodes": []}


@pytest.mark.parametrize("field", ["owner", "caller", "content", "grants", "unexpected"])
def test_upload_rejects_authority_and_unknown_fields(
    filesystem_http: FilesystemHttp, upload_path: str, field: str,
) -> None:
    response = filesystem_http.client.post(upload_path, files={
        "file": ("injected.bin", b"payload", "application/octet-stream"),
    }, data={field: "injected"})
    assert response.status_code == 422
    assert filesystem_http.client.get(upload_path.removesuffix("/files") + "/children").json() == {"nodes": []}


@pytest.mark.parametrize("parts", [
    [("name", (None, "missing.bin"))],
    [("file", (None, "not-a-file"))],
    [("other", ("wrong.bin", b"data", "application/octet-stream"))],
    [("file", ("a.bin", b"a", "application/octet-stream")), ("file", ("b.bin", b"b", "application/octet-stream"))],
    [("file", ("a.bin", b"a", "application/octet-stream")), ("name", (None, "one")), ("name", (None, "two"))],
    [("file", ("a.bin", b"a", "application/octet-stream")), ("metadata", (None, "{}")), ("metadata", (None, "{}"))],
    [("file", ("a.bin", b"a", "application/octet-stream")), ("name", ("name.txt", b"name", "text/plain"))],
])
def test_upload_requires_exactly_one_file_and_unique_text_fields(
    filesystem_http: FilesystemHttp, upload_path: str, parts: list[MultipartPart],
) -> None:
    response = filesystem_http.client.post(upload_path, files=parts)
    assert response.status_code == 422
    assert filesystem_http.client.get(upload_path.removesuffix("/files") + "/children").json() == {"nodes": []}


@pytest.mark.parametrize("content_type,payload", [
    ("multipart/form-data", b"malformed"),
    ("multipart/form-data; boundary=upload", b"--upload\r\nincomplete"),
    ("multipart/form-data; boundary=upload", b""),
])
def test_malformed_multipart_is_validation_error(
    filesystem_http: FilesystemHttp, upload_path: str, content_type: str, payload: bytes,
) -> None:
    response = filesystem_http.client.post(upload_path, content=payload, headers={"Content-Type": content_type})
    assert response.status_code == 422


def test_upload_conflict_keeps_original_bytes(
    filesystem_http: FilesystemHttp, upload_path: str,
) -> None:
    original = filesystem_http.client.post(upload_path, files={"file": ("same.bin", b"first")})
    assert original.status_code == 201
    duplicate = filesystem_http.client.post(upload_path, files={"file": ("same.bin", b"second")})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "filesystem_name_collision"
    assert filesystem_http.client.get(content_path(original.json()["id"])).content == b"first"
    assert len(filesystem_http.client.get(upload_path.removesuffix("/files") + "/children").json()["nodes"]) == 1


@pytest.mark.parametrize("kind", ["files", "directories"])
def test_empty_upload_download_and_directory_conflict(
    filesystem_http: FilesystemHttp, upload_path: str, kind: str,
) -> None:
    created = filesystem_http.client.post(
        upload_path.removesuffix("/files") + "/" + kind, **creation_payload(kind, BODY),
    )
    assert created.status_code == 201
    downloaded = filesystem_http.client.get(content_path(created.json()["id"]))
    if kind == "files":
        assert downloaded.status_code == 200
        assert downloaded.content == b""
    else:
        assert downloaded.status_code == 409
        assert downloaded.json()["detail"]["code"] == "filesystem_wrong_node_kind"


def test_private_content_and_missing_content_are_indistinguishable(
    filesystem_http: FilesystemHttp, upload_path: str,
) -> None:
    uploaded = filesystem_http.client.post(upload_path, files={"file": ("private.bin", b"secret")})
    assert uploaded.status_code == 201
    denied = filesystem_http.client.get(content_path(uploaded.json()["id"]), headers={"Authorization": "Bearer bob"})
    missing = filesystem_http.client.get(content_path(str(uuid4())), headers={"Authorization": "Bearer bob"})
    assert denied.status_code == missing.status_code == 403
    assert denied.json() == missing.json()
    assert denied.json()["detail"]["code"] == "filesystem_permission_denied"
    assert denied.headers["cache-control"] == "no-store"
    rejected = filesystem_http.client.post(
        f"{BASE}/nodes/{uploaded.json()['id']}/files", files={"file": ("child.bin", b"secret")},
        headers={"Authorization": "Bearer bob"},
    )
    assert rejected.status_code == 403


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_content_requires_authentication_and_verified_identity(
    filesystem_http: FilesystemHttp, upload_path: str, method: str,
) -> None:
    path = upload_path if method == "POST" else content_path(str(uuid4()))
    anonymous = filesystem_http.client.request(method, path, headers={"Authorization": ""})
    assert anonymous.status_code == 401
    assert anonymous.headers["cache-control"] == "no-store"
    del filesystem_http.app.dependency_overrides[get_caller_context]
    unverified = filesystem_http.client.request(method, path, files={"file": ("test.bin", b"data")})
    assert unverified.status_code == 403
    assert unverified.json()["detail"]["code"] == "filesystem_permission_denied"


def test_multipart_upload_requires_cookie_csrf_protection(
    filesystem_http: FilesystemHttp, upload_path: str,
) -> None:
    client = filesystem_http.client
    blocked = client.post(upload_path, files={"file": ("csrf.bin", b"safe")}, headers={"Cookie": "session=present"})
    assert blocked.status_code == 403
    allowed = client.post(upload_path, files={"file": ("csrf.bin", b"safe")}, headers={
        "Cookie": "session=present",
        "Origin": str(filesystem_http.factories.settings.endpoints.site_base_url).rstrip("/"),
        "X-Umbod-Web-Request": "1",
    })
    assert allowed.status_code == 201
    assert client.get(content_path(allowed.json()["id"])).content == b"safe"


@pytest.mark.parametrize("filesystem_upload_max_bytes", [8], indirect=True)
@pytest.mark.parametrize("size,status", [(8, 201), (9, 413)])
@pytest.mark.parametrize("chunked", [False, True])
def test_upload_limit_counts_bytes_with_and_without_content_length(
    filesystem_http: FilesystemHttp, upload_path: str,
    filesystem_upload_max_bytes: int, size: int, status: int, chunked: bool,
) -> None:
    payload = b"x" * size
    if chunked:
        response = filesystem_http.client.post(upload_path, content=multipart_chunks(payload), headers={
            "Content-Type": "multipart/form-data; boundary=upload",
        })
        assert "content-length" not in response.request.headers
    else:
        response = filesystem_http.client.post(upload_path, files={"file": ("limited.bin", payload)})
    assert filesystem_upload_max_bytes == 8
    assert response.status_code == status
    children = filesystem_http.client.get(upload_path.removesuffix("/files") + "/children").json()["nodes"]
    assert len(children) == (1 if status == 201 else 0)
    if status == 201:
        assert filesystem_http.client.get(content_path(response.json()["id"])).content == payload


class RecordingContentDriver:
    def __init__(self) -> None:
        self.content = create_content_driver(InMemoryContentConfig(type="inmemory"))
        self.uploads = 0
        self.downloads = 0

    async def put(self, data: ByteStream) -> ContentRef:
        self.uploads += 1
        return await self.content.put(data)

    async def get(self, key: StorageKey) -> ByteStream:
        self.downloads += 1
        async for chunk in self.content.get(key):
            yield chunk


def test_injected_content_driver_handles_upload_and_download(
    filesystem_http: FilesystemHttp, upload_path: str,
) -> None:
    driver = RecordingContentDriver()

    def provide_driver() -> RecordingContentDriver:
        return driver

    filesystem_http.app.dependency_overrides[get_filesystem_content_driver] = provide_driver
    uploaded = filesystem_http.client.post(upload_path, files={"file": ("injected.bin", b"injected storage")})
    assert uploaded.status_code == 201
    downloaded = filesystem_http.client.get(content_path(uploaded.json()["id"]))
    assert downloaded.status_code == 200
    assert downloaded.content == b"injected storage"
    assert driver.uploads == driver.downloads == 1
    denied = filesystem_http.client.get(content_path(uploaded.json()["id"]), headers={"Authorization": "Bearer bob"})
    assert denied.status_code == 403
    assert driver.downloads == 1
