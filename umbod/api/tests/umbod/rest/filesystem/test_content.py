from collections.abc import Iterator
from datetime import timedelta
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from umbod.core.filesystem import ByteStream, ContentRef, StorageKey
from umbod.infrastructure import InMemoryContentConfig, create_content_driver
from umbod.rest.filesystem.deps import get_filesystem_content_driver, get_filesystem_upload_clock
from tests.umbod.core.filesystem.test_upload_sessions import Clock

from .conftest import FilesystemHttp
from .test_http_contract import BASE


@pytest.fixture
def upload_path(filesystem_http: FilesystemHttp) -> str:
    root_id = filesystem_http.client.get(f"{BASE}/root").json()["id"]
    return f"{BASE}/nodes/{root_id}/uploads"


def content_path(identifier: str) -> str:
    return f"{BASE}/nodes/{identifier}/content"


def begin_upload(client: TestClient, path: str, name: str, payload: bytes) -> Response:
    return begin_typed_upload(client, path, name, payload, "application/octet-stream")


def begin_typed_upload(client: TestClient, path: str, name: str, payload: bytes, content_type: object) -> Response:
    return client.post(path, json={
        "name": name, "metadata": {"content_type": content_type, "attributes": {}}, "size_bytes": len(payload),
    })


def upload_file(client: TestClient, path: str, name: str, payload: bytes) -> Response:
    return upload_typed_file(client, path, name, payload, "application/octet-stream")


def upload_typed_file(client: TestClient, path: str, name: str, payload: bytes, content_type: object) -> Response:
    begun = begin_typed_upload(client, path, name, payload, content_type).json()
    response = client.put(begun["transfer"]["url"], content=payload, headers=begun["transfer"]["headers"])
    assert response.status_code == 204
    return client.post(begun["complete_url"])


@pytest.mark.parametrize("payload", [b"\x00\xff\x80binary\r\n\x00", b""])
def test_upload_download_preserves_bytes_and_safe_headers(filesystem_http: FilesystemHttp, upload_path: str, payload: bytes) -> None:
    uploaded = upload_file(filesystem_http.client, upload_path, "payload.bin", payload)
    assert uploaded.status_code == 201
    node = uploaded.json()
    assert uploaded.headers["location"] == f"{BASE}/nodes/{node['id']}"
    assert uploaded.headers["cache-control"] == "no-store"
    assert set(node) == {"id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision"}
    downloaded = filesystem_http.client.get(content_path(node["id"]))
    assert downloaded.content == payload
    assert downloaded.headers["content-type"] == "application/octet-stream"
    assert downloaded.headers["cache-control"] == "no-store"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["content-disposition"].startswith("attachment;")


def test_unicode_name_uses_safe_utf8_attachment_filename(filesystem_http: FilesystemHttp, upload_path: str) -> None:
    filename = 'résumé-東京-"notes".bin'
    uploaded = upload_file(filesystem_http.client, upload_path, filename, b"unicode")
    downloaded = filesystem_http.client.get(content_path(uploaded.json()["id"]))
    disposition = downloaded.headers["content-disposition"]
    assert "filename*=UTF-8''" + quote(filename, safe="") in disposition
    assert "\r" not in disposition and "\n" not in disposition
    assert downloaded.content == b"unicode"


@pytest.mark.parametrize("content_type", ["application/custom", {}])
def test_metadata_content_type_and_fallback(filesystem_http: FilesystemHttp, upload_path: str, content_type: object) -> None:
    uploaded = upload_typed_file(filesystem_http.client, upload_path, "file", b"payload", content_type)
    assert uploaded.status_code == 201
    assert uploaded.json()["metadata"]["content_type"] == content_type
    assert filesystem_http.client.get(content_path(uploaded.json()["id"])).content == b"payload"


def test_session_wire_contract_and_idempotent_completion(filesystem_http: FilesystemHttp, upload_path: str) -> None:
    client = filesystem_http.client
    begun = begin_upload(client, upload_path, "file", b"abc")
    assert begun.status_code == 201
    session = begun.json()
    assert set(session) == {"id", "expires_at", "status", "transfer", "complete_url"}
    UUID(session["id"])
    assert session["status"] == "pending"
    assert session["transfer"] == {
        "type": "single", "method": "PUT", "url": f"{BASE}/uploads/{session['id']}/content",
        "headers": {"Content-Type": "application/octet-stream"}, "authorization": {"type": "same_origin"},
    }
    assert begun.headers["location"] == f"{BASE}/uploads/{session['id']}"
    assert client.get(begun.headers["location"]).json() == session
    assert client.get(upload_path.removesuffix("/uploads") + "/children").json() == {"nodes": []}
    assert client.post(session["complete_url"]).status_code == 409
    assert client.put(session["transfer"]["url"], content=b"abc", headers=session["transfer"]["headers"]).status_code == 204
    assert client.get(begun.headers["location"]).json()["status"] == "uploaded"
    assert client.get(upload_path.removesuffix("/uploads") + "/children").json() == {"nodes": []}
    completed = client.post(session["complete_url"])
    retry = client.post(session["complete_url"])
    assert completed.status_code == 201 and retry.status_code == 200
    assert retry.json() == completed.json()
    assert retry.headers["location"] == completed.headers["location"]
    assert client.get(begun.headers["location"]).json()["status"] == "completed"
    assert client.put(session["transfer"]["url"], content=b"new", headers=session["transfer"]["headers"]).status_code == 409
    assert client.get(content_path(completed.json()["id"])).content == b"abc"


@pytest.mark.parametrize("field", ["owner", "caller", "content", "grants", "unexpected"])
@pytest.mark.parametrize("nested", [False, True])
def test_begin_rejects_authority_and_unknown_fields(filesystem_http: FilesystemHttp, upload_path: str, field: str, nested: bool) -> None:
    body = {"name": "file", "metadata": {"content_type": {}, "attributes": {}}, "size_bytes": 0}
    if nested:
        body["metadata"][field] = "injected"
    else:
        body[field] = "injected"
    assert filesystem_http.client.post(upload_path, json=body).status_code == 422


@pytest.mark.parametrize("size", [-1, True, 1.0, "1", None])
def test_declared_size_is_strict_nonnegative_integer(filesystem_http: FilesystemHttp, upload_path: str, size: object) -> None:
    response = filesystem_http.client.post(upload_path, json={
        "name": "file", "metadata": {"content_type": {}, "attributes": {}}, "size_bytes": size,
    })
    assert response.status_code == 422


@pytest.mark.parametrize("filesystem_upload_max_bytes", [8], indirect=True)
def test_begin_enforces_configured_limit(filesystem_http: FilesystemHttp, upload_path: str, filesystem_upload_max_bytes: int) -> None:
    assert filesystem_upload_max_bytes == 8
    assert begin_upload(filesystem_http.client, upload_path, "large", b"x" * 9).status_code == 413


@pytest.mark.parametrize("payload,status", [(b"abc", 204), (b"ab", 422), (b"abcd", 413)])
@pytest.mark.parametrize("chunked", [False, True])
def test_transfer_counts_actual_bytes_and_full_retry_is_allowed(filesystem_http: FilesystemHttp, upload_path: str, payload: bytes, status: int, chunked: bool) -> None:
    client = filesystem_http.client
    session = begin_upload(client, upload_path, "file", b"abc").json()

    def chunks() -> Iterator[bytes]:
        for value in payload:
            yield bytes([value])

    response = client.put(session["transfer"]["url"], content=chunks() if chunked else payload, headers=session["transfer"]["headers"])
    assert response.status_code == status
    if chunked:
        assert "content-length" not in response.request.headers
    if status != 204:
        assert client.put(session["transfer"]["url"], content=b"abc", headers=session["transfer"]["headers"]).status_code == 204
    assert client.post(session["complete_url"]).status_code == 201


def test_mismatched_content_type_returns_415_before_transfer(filesystem_http: FilesystemHttp, upload_path: str) -> None:
    client = filesystem_http.client
    session = begin_typed_upload(client, upload_path, "file", b"abc", "text/plain").json()
    assert client.put(session["transfer"]["url"], content=b"abc", headers={"Content-Type": "application/json"}).status_code == 415
    assert client.post(session["complete_url"]).status_code == 409


def test_name_collision_does_not_overwrite_original(filesystem_http: FilesystemHttp, upload_path: str) -> None:
    client = filesystem_http.client
    first = upload_file(client, upload_path, "same", b"first")
    assert first.status_code == 201
    assert upload_file(client, upload_path, "same", b"second").status_code == 409
    assert client.get(content_path(first.json()["id"])).content == b"first"


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("PUT", "/content"), ("POST", "/complete")])
def test_private_and_missing_sessions_are_indistinguishable(filesystem_http: FilesystemHttp, upload_path: str, method: str, suffix: str) -> None:
    client = filesystem_http.client
    session = begin_upload(client, upload_path, "private", b"x").json()
    private = client.request(method, f"{BASE}/uploads/{session['id']}{suffix}", headers={"Authorization": "Bearer bob"})
    missing = client.request(method, f"{BASE}/uploads/{uuid4()}{suffix}", headers={"Authorization": "Bearer bob"})
    assert private.status_code == missing.status_code == 403
    assert private.json() == missing.json()


@pytest.mark.parametrize("stage", ["begin", "put", "complete"])
def test_all_upload_mutations_keep_cookie_csrf(filesystem_http: FilesystemHttp, upload_path: str, stage: str) -> None:
    client = filesystem_http.client
    cookie = {"Cookie": "session=present"}
    approved = {**cookie, "Origin": str(filesystem_http.factories.settings.endpoints.site_base_url).rstrip("/"), "X-Umbod-Web-Request": "1"}
    if stage == "begin":
        body = {"name": "file", "metadata": {"content_type": {}, "attributes": {}}, "size_bytes": 0}
        assert client.post(upload_path, json=body, headers=cookie).status_code == 403
        assert client.post(upload_path, json=body, headers=approved).status_code == 201
        return
    session = begin_upload(client, upload_path, "file", b"x").json()
    transfer = session["transfer"]
    if stage == "put":
        assert client.put(transfer["url"], content=b"x", headers={**cookie, **transfer["headers"]}).status_code == 403
        assert client.put(transfer["url"], content=b"x", headers={**approved, **transfer["headers"]}).status_code == 204
    else:
        assert client.put(transfer["url"], content=b"x", headers=transfer["headers"]).status_code == 204
        assert client.post(session["complete_url"], headers=cookie).status_code == 403
        assert client.post(session["complete_url"], headers=approved).status_code == 201


def test_expired_incomplete_session_returns_410(filesystem_http: FilesystemHttp, upload_path: str) -> None:
    from datetime import datetime, timezone

    clock = Clock(datetime(2026, 1, 1, tzinfo=timezone.utc))

    def provide_clock() -> Clock:
        return clock

    filesystem_http.app.dependency_overrides[get_filesystem_upload_clock] = provide_clock
    session = begin_upload(filesystem_http.client, upload_path, "expired", b"x").json()
    clock.current += timedelta(hours=1)
    for method, path in [("GET", f"{BASE}/uploads/{session['id']}"), ("PUT", session["transfer"]["url"]), ("POST", session["complete_url"])]:
        assert filesystem_http.client.request(method, path).status_code == 410


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


def test_injected_content_driver_handles_upload_and_download(filesystem_http: FilesystemHttp, upload_path: str) -> None:
    driver = RecordingContentDriver()

    def provide_driver() -> RecordingContentDriver:
        return driver

    filesystem_http.app.dependency_overrides[get_filesystem_content_driver] = provide_driver
    uploaded = upload_file(filesystem_http.client, upload_path, "injected", b"injected storage")
    assert uploaded.status_code == 201
    assert filesystem_http.client.get(content_path(uploaded.json()["id"])).content == b"injected storage"
    assert driver.uploads == driver.downloads == 1
    assert filesystem_http.client.get(content_path(uploaded.json()["id"]), headers={"Authorization": "Bearer bob"}).status_code == 403
    assert driver.downloads == 1
