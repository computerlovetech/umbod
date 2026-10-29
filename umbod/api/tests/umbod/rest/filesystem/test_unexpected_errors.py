from collections.abc import Iterator
from unittest.mock import Mock, create_autospec
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from umbod.core.filesystem import FilesystemCreation
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.uploads import UploadService
from umbod.rest.filesystem import deps

from .conftest import FilesystemHttp
from .test_http_contract import BASE, BODY, creation_payload
from .test_ports_and_dependencies import OPERATIONS


@pytest.fixture
def nonraising_client(filesystem_http: FilesystemHttp) -> Iterator[TestClient]:
    client = TestClient(
        filesystem_http.root, raise_server_exceptions=False,
        headers={"Authorization": "Bearer alice"},
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.parametrize("method,path,operation", OPERATIONS)
@pytest.mark.parametrize("failure", ["service", "serialization"])
def test_unexpected_service_and_response_errors_are_safe_and_no_store(
    filesystem_http: FilesystemHttp, nonraising_client: TestClient,
    method: str, path: str, operation: str, failure: str,
) -> None:
    browsing = create_autospec(FilesystemBrowsing, instance=True)
    creation = create_autospec(FilesystemCreation, instance=True)
    content = create_autospec(UploadService, instance=True)
    service = content if operation == "begin" else creation if method == "POST" else browsing
    if failure == "service":
        getattr(service, operation).side_effect = RuntimeError("private storage/key credential")
    else:
        getattr(service, operation).return_value = {"credential": "private storage/key"}

    def provide_browsing() -> FilesystemBrowsing:
        return browsing

    def provide_creation() -> FilesystemCreation:
        return creation

    def provide_content() -> UploadService:
        return content

    filesystem_http.app.dependency_overrides[deps.get_filesystem_uploads] = provide_content
    filesystem_http.app.dependency_overrides[deps.get_filesystem_browsing] = provide_browsing
    filesystem_http.app.dependency_overrides[deps.get_filesystem_creation] = provide_creation
    response = nonraising_client.request(
        method, BASE + path.format(id=uuid4()),
        **creation_payload("uploads" if path.endswith("/uploads") else "directories", BODY),
    )
    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": {"code": "internal_server_error", "message": "Request failed."}}


@pytest.mark.parametrize("factory,method,path", [
    ("create_filesystem_browsing", "GET", "/root"),
    ("create_filesystem_uploads", "POST", "/nodes/{id}/uploads"),
    ("create_filesystem_creation", "POST", "/nodes/{id}/directories"),
])
def test_unexpected_service_factory_errors_are_safe_and_no_store(
    filesystem_http: FilesystemHttp, nonraising_client: TestClient,
    monkeypatch: pytest.MonkeyPatch, factory: str, method: str, path: str,
) -> None:
    failing_factory = Mock(side_effect=RuntimeError("private factory credential"))
    monkeypatch.setattr(deps, factory, failing_factory)
    response = nonraising_client.request(
        method, BASE + path.format(id=uuid4()),
        **creation_payload("uploads" if path.endswith("/uploads") else "directories", BODY),
    )
    assert failing_factory.call_count == 1
    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": {"code": "internal_server_error", "message": "Request failed."}}


@pytest.mark.parametrize("method,path,operation", OPERATIONS)
def test_unexpected_readiness_errors_are_safe_and_no_store(
    filesystem_http: FilesystemHttp, nonraising_client: TestClient,
    monkeypatch: pytest.MonkeyPatch, method: str, path: str, operation: str,
) -> None:
    async def failing_readiness() -> None:
        raise RuntimeError("private database credential")

    monkeypatch.setattr(filesystem_http.factories.persistence_runtime.readiness, "ensure_ready", failing_readiness)
    response = nonraising_client.request(
        method, BASE + path.format(id=uuid4()),
        **creation_payload("uploads" if path.endswith("/uploads") else "directories", BODY),
    )
    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": {"code": "internal_server_error", "message": "Request failed."}}
