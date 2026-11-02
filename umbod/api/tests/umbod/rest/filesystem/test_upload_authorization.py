from uuid import UUID, uuid4

import pytest

from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.persistence import Database
from umbod.infrastructure import create_access_control_driver
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.filesystem.deps import get_filesystem_database

from .conftest import FilesystemHttp
from .test_content import upload_file
from .test_http_contract import BASE, BODY


@pytest.fixture
def upload_parent(filesystem_http: FilesystemHttp) -> str:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/browse").json()["node"]["id"]
    response = client.post(f"{BASE}/nodes/{root_id}/directories", json=BODY)
    assert response.status_code == 201
    return response.json()["id"]


def upload_path(parent_id: str) -> str:
    return f"{BASE}/nodes/{parent_id}/uploads"


def test_removed_upload_options_and_root_do_not_resolve_storage(filesystem_http: FilesystemHttp) -> None:
    def forbid_database() -> Database:
        pytest.fail("Removed routes must not resolve filesystem storage")

    filesystem_http.app.dependency_overrides[get_filesystem_database] = forbid_database
    client = filesystem_http.client
    root = client.get(f"{BASE}/root")
    assert root.status_code == 404
    assert root.headers["cache-control"] == "no-store"
    options = client.options(upload_path(str(uuid4())))
    assert options.status_code == 405
    assert options.headers["allow"] == "POST"
    assert options.headers["cache-control"] == "no-store"
    paths = client.get("/api/me/openapi.json").json()["paths"]
    assert "/filesystem/root" not in paths
    assert set(paths["/filesystem/nodes/{parent_id}/uploads"]) == {"post"}
    assert "get" in paths["/filesystem/uploads/{upload_id}"]


def test_upload_cors_preflight_is_not_an_authorized_options_handler(filesystem_http: FilesystemHttp) -> None:
    origin = filesystem_http.factories.settings.cors.origins[0]
    response = filesystem_http.client.options(upload_path(str(uuid4())), headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] in (origin, "*")
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "allow" not in response.headers


def test_readable_directory_does_not_imply_upload_authority(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    client = filesystem_http.client
    policies = create_access_control_driver(database=filesystem_http.factories.persistence_runtime.database)
    client.portal.call(policies.add_grant, AccessGrant(
        node_id=UUID(upload_parent),
        principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
        permissions={Permission.DISCOVER, Permission.READ}, recursive=False,
    ))
    bob = {"Authorization": "Bearer bob"}
    assert client.get(f"{BASE}/nodes/{upload_parent}", headers=bob).status_code == 200
    response = client.post(upload_path(upload_parent), json={**BODY, "size_bytes": 0}, headers=bob)
    missing = client.post(upload_path(str(uuid4())), json={**BODY, "size_bytes": 0}, headers=bob)
    assert response.status_code == missing.status_code == 403
    assert response.json() == missing.json()
    assert response.json()["detail"]["code"] == "filesystem_permission_denied"


def test_private_and_missing_upload_parents_are_indistinguishable(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    client = filesystem_http.client
    bob = {"Authorization": "Bearer bob"}
    private = client.post(upload_path(upload_parent), json={**BODY, "size_bytes": 0}, headers=bob)
    missing = client.post(upload_path(str(uuid4())), json={**BODY, "size_bytes": 0}, headers=bob)
    assert private.status_code == missing.status_code == 403
    assert private.json() == missing.json()
    assert private.json()["detail"]["code"] == "filesystem_permission_denied"


def test_file_upload_parent_returns_wrong_node_kind(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    uploaded = upload_file(filesystem_http.client, upload_path(upload_parent), "file.bin", b"payload")
    assert uploaded.status_code == 201
    response = filesystem_http.client.post(upload_path(uploaded.json()["id"]), json={**BODY, "size_bytes": 0})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "filesystem_wrong_node_kind"


def test_unverified_upload_begin_matches_missing_denial(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    client = filesystem_http.client
    missing = client.post(upload_path(str(uuid4())), json={**BODY, "size_bytes": 0})
    del filesystem_http.app.dependency_overrides[get_caller_context]
    response = client.post(upload_path(upload_parent), json={**BODY, "size_bytes": 0})
    assert response.status_code == missing.status_code == 403
    assert response.json() == missing.json()


def test_anonymous_upload_begin_requires_authentication(
    filesystem_http: FilesystemHttp, upload_parent: str,
) -> None:
    response = filesystem_http.client.post(
        upload_path(upload_parent), json={**BODY, "size_bytes": 0}, headers={"Authorization": ""},
    )
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
