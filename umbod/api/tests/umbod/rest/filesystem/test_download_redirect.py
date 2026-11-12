from uuid import uuid4

import pytest

from umbod.core.filesystem import ContentDriver
from umbod.rest.filesystem.deps import get_filesystem_content_driver
from tests.support.filesystem.downloads import DirectDownloadContent

from .conftest import FilesystemHttp
from .test_content import upload_typed_file
from .test_http_contract import BASE


@pytest.fixture
def direct_content(filesystem_http: FilesystemHttp) -> DirectDownloadContent:
    driver = DirectDownloadContent()

    def provide_content() -> ContentDriver:
        return driver

    filesystem_http.app.dependency_overrides[get_filesystem_content_driver] = provide_content
    return driver


def uploaded_path(http: FilesystemHttp) -> str:
    root = http.client.get(BASE + "/browse").json()["node"]["id"]
    uploaded = upload_typed_file(http.client, BASE + "/nodes/" + root + "/uploads", "notes.md", b"# Notes", "text/markdown")
    assert uploaded.status_code == 201
    return BASE + "/nodes/" + uploaded.json()["id"] + "/content"


def test_download_redirect_is_temporary_private_and_does_not_read_storage(
    filesystem_http: FilesystemHttp, direct_content: DirectDownloadContent,
) -> None:
    path = uploaded_path(filesystem_http)
    before = len(direct_content.read_keys)
    response = filesystem_http.client.get(path, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://storage.example.test/object?signature=secret"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert len(direct_content.read_keys) == before
    assert len(direct_content.download_requests) == 1
    assert response.content == b""


def test_explicit_stream_delivery_preserves_authorized_preview_bytes(
    filesystem_http: FilesystemHttp, direct_content: DirectDownloadContent,
) -> None:
    path = uploaded_path(filesystem_http)
    response = filesystem_http.client.get(path + "?delivery=stream", follow_redirects=False)
    assert response.status_code == 200
    assert response.content == b"# Notes"
    assert response.headers["content-type"].startswith("text/markdown")
    assert "location" not in response.headers
    assert direct_content.download_requests == []


@pytest.mark.parametrize("identity", ["bob", "outsider"])
@pytest.mark.parametrize("delivery", ["auto", "stream"])
def test_denied_download_never_signs_or_redirects(
    filesystem_http: FilesystemHttp, direct_content: DirectDownloadContent, identity: str, delivery: str,
) -> None:
    path = uploaded_path(filesystem_http)
    response = filesystem_http.client.get(path + "?delivery=" + delivery, headers={"Authorization": "Bearer " + identity}, follow_redirects=False)
    assert response.status_code == 403
    assert "location" not in response.headers
    assert direct_content.download_requests == []


def test_missing_download_never_signs_or_redirects(
    filesystem_http: FilesystemHttp, direct_content: DirectDownloadContent,
) -> None:
    response = filesystem_http.client.get(BASE + "/nodes/" + str(uuid4()) + "/content", follow_redirects=False)
    assert response.status_code == 403
    assert "location" not in response.headers
    assert direct_content.download_requests == []


def test_signing_failure_returns_sanitized_error_without_falling_back_to_storage_reads(
    filesystem_http: FilesystemHttp, direct_content: DirectDownloadContent,
) -> None:
    path = uploaded_path(filesystem_http)
    direct_content.fail_signing = True
    before = len(direct_content.read_keys)
    response = filesystem_http.client.get(path, follow_redirects=False)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "filesystem_storage_failure"
    assert "private" not in response.text
    assert "location" not in response.headers
    assert len(direct_content.read_keys) == before


def test_invalid_delivery_mode_is_rejected(
    filesystem_http: FilesystemHttp, direct_content: DirectDownloadContent,
) -> None:
    response = filesystem_http.client.get(uploaded_path(filesystem_http) + "?delivery=external", follow_redirects=False)
    assert response.status_code == 422
    assert direct_content.download_requests == []
