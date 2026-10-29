from uuid import UUID, uuid4

import pytest

from umbod.core.filesystem import AccessGrant, Ownership, Permission, Principal, PrincipalType
from umbod.infrastructure import create_access_control_driver
from umbod.rest.authentication.deps import get_caller_context
from umbod.rest.filesystem.deps import get_filesystem_content_driver

from .conftest import FilesystemHttp
from .test_content import RecordingContentDriver, begin_upload, upload_file
from .test_http_contract import BASE, BODY


@pytest.fixture
def published_file(filesystem_http: FilesystemHttp) -> dict[str, object]:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/root").json()["id"]
    response = upload_file(client, f"{BASE}/nodes/{root_id}/uploads", "file.bin", b"payload")
    assert response.status_code == 201
    return response.json()


def test_file_etag_options_and_permanent_removal_without_content_io(
    filesystem_http: FilesystemHttp, published_file: dict[str, object],
) -> None:
    client = filesystem_http.client
    path = f"{BASE}/nodes/{published_file['id']}"
    before = client.get(path)
    etag = before.headers["etag"]
    assert etag == f'"{published_file["revision"]}"'
    driver = RecordingContentDriver()

    def provide_driver() -> RecordingContentDriver:
        return driver

    filesystem_http.app.dependency_overrides[get_filesystem_content_driver] = provide_driver
    policies = create_access_control_driver(database=filesystem_http.factories.persistence_runtime.database)
    node_id = UUID(str(published_file["id"]))
    owner = client.portal.call(policies.get_owner, node_id)
    grants = client.portal.call(policies.list_grants, node_id)
    options = client.options(path)
    assert options.status_code == 204 and options.content == b""
    assert set(options.headers["allow"].split(", ")) == {"GET", "DELETE", "OPTIONS"}
    assert options.headers["cache-control"] == "no-store"
    assert client.get(path).json() == before.json()
    assert client.portal.call(policies.get_owner, node_id) == owner
    assert client.portal.call(policies.list_grants, node_id) == grants
    response = client.delete(path, headers={"If-Match": etag})
    assert response.status_code == 204 and response.content == b""
    assert response.headers["cache-control"] == "no-store"
    assert driver.uploads == driver.downloads == 0
    assert client.get(path).status_code == 403
    assert client.delete(path, headers={"If-Match": etag}).status_code == 403
    assert client.options(path).status_code == 403
    children = client.get(f"{BASE}/nodes/{published_file['parent_id']}/children").json()["nodes"]
    assert children == []


@pytest.mark.parametrize("revision", [
    '2', '"0"', '"-1"', 'W/"2"', '*', '"2", "3"', '"02"', '"abc"', '',
    pytest.param('"' + '9' * 5000 + '"', id="oversized-revision"),
])
def test_delete_rejects_unsupported_conditional_forms(
    filesystem_http: FilesystemHttp, published_file: dict[str, object], revision: str,
) -> None:
    path = f"{BASE}/nodes/{published_file['id']}"
    response = filesystem_http.client.delete(path, headers={"If-Match": revision})
    assert response.status_code == 422
    assert filesystem_http.client.get(path).json() == published_file


def test_missing_duplicate_and_stale_preconditions(
    filesystem_http: FilesystemHttp, published_file: dict[str, object],
) -> None:
    client = filesystem_http.client
    path = f"{BASE}/nodes/{published_file['id']}"
    assert client.delete(path).status_code == 428
    assert client.delete(path, headers=[("If-Match", '"2"'), ("If-Match", '"2"')]).status_code == 422
    response = client.delete(path, headers={"If-Match": '"1"'})
    assert response.status_code == 412
    assert response.json()["detail"]["code"] == "filesystem_revision_conflict"
    assert client.get(path).json() == published_file


@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.DELETE}, {Permission.DISCOVER, Permission.READ}])
def test_delete_denials_and_missing_nodes_are_indistinguishable(
    filesystem_http: FilesystemHttp, published_file: dict[str, object], permissions: set[Permission],
) -> None:
    client = filesystem_http.client
    policies = create_access_control_driver(database=filesystem_http.factories.persistence_runtime.database)
    client.portal.call(policies.add_grant, AccessGrant(
        node_id=UUID(str(published_file["id"])),
        principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
        permissions=permissions, recursive=False,
    ))
    for method in ("OPTIONS", "DELETE"):
        headers = {"Authorization": "Bearer bob", "If-Match": '"999"'}
        denied = client.request(method, f"{BASE}/nodes/{published_file['id']}", headers=headers)
        missing = client.request(method, f"{BASE}/nodes/{uuid4()}", headers=headers)
        assert denied.status_code == missing.status_code == 403
        assert denied.json() == missing.json()
        assert denied.json()["detail"]["code"] == "filesystem_permission_denied"
        assert denied.headers["cache-control"] == "no-store"


def test_authorization_revoked_after_eligibility_is_checked_again(
    filesystem_http: FilesystemHttp, published_file: dict[str, object],
) -> None:
    client = filesystem_http.client
    node_id = UUID(str(published_file["id"]))
    path = f"{BASE}/nodes/{node_id}"
    policies = create_access_control_driver(database=filesystem_http.factories.persistence_runtime.database)
    bob = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    client.portal.call(policies.add_grant, AccessGrant(
        node_id=node_id, principal=bob, permissions={Permission.DISCOVER, Permission.DELETE}, recursive=False,
    ))
    headers = {"Authorization": "Bearer bob", "If-Match": f'"{published_file["revision"]}"'}
    assert client.options(path, headers=headers).status_code == 204
    client.portal.call(policies.remove_grant, node_id, bob)
    assert client.delete(path, headers=headers).status_code == 403
    assert client.get(path).json() == published_file


@pytest.mark.parametrize("root", [False, True])
def test_authorized_directory_and_root_are_not_deletable(filesystem_http: FilesystemHttp, root: bool) -> None:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/root").json()["id"]
    if root:
        node_id = root_id
        policies = create_access_control_driver(database=filesystem_http.factories.persistence_runtime.database)
        client.portal.call(policies.set_owner, Ownership(
            node_id=UUID(root_id), owner=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"),
        ))
    else:
        node_id = client.post(f"{BASE}/nodes/{root_id}/directories", json=BODY).json()["id"]
    path = f"{BASE}/nodes/{node_id}"
    for method in ("OPTIONS", "DELETE"):
        response = client.request(method, path, headers={"If-Match": '"999"'})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "filesystem_wrong_node_kind"
    assert client.get(path).status_code == 200


def test_delete_and_options_require_authentication_and_verified_identity(
    filesystem_http: FilesystemHttp, published_file: dict[str, object],
) -> None:
    client = filesystem_http.client
    path = f"{BASE}/nodes/{published_file['id']}"
    for method in ("OPTIONS", "DELETE"):
        response = client.request(method, path, headers={"Authorization": "", "If-Match": '"2"'})
        assert response.status_code == 401
    del filesystem_http.app.dependency_overrides[get_caller_context]
    for method in ("OPTIONS", "DELETE"):
        response = client.request(method, path, headers={"If-Match": '"2"'})
        assert response.status_code == 403


def test_delete_keeps_cookie_csrf_protection(filesystem_http: FilesystemHttp, published_file: dict[str, object]) -> None:
    client = filesystem_http.client
    path = f"{BASE}/nodes/{published_file['id']}"
    headers = {"If-Match": f'"{published_file["revision"]}"', "Cookie": "session=present"}
    assert client.delete(path, headers=headers).status_code == 403
    assert client.get(path).status_code == 200
    allowed = client.delete(path, headers={
        **headers, "Origin": str(filesystem_http.factories.settings.endpoints.site_base_url).rstrip("/"),
        "X-Umbod-Web-Request": "1",
    })
    assert allowed.status_code == 204


def test_completed_upload_retry_cannot_restore_deleted_file(filesystem_http: FilesystemHttp) -> None:
    client = filesystem_http.client
    root_id = client.get(f"{BASE}/root").json()["id"]
    begun = begin_upload(client, f"{BASE}/nodes/{root_id}/uploads", "file.bin", b"x").json()
    assert client.put(begun["transfer"]["url"], content=b"x", headers=begun["transfer"]["headers"]).status_code == 204
    published = client.post(begun["complete_url"])
    assert published.status_code == 201
    node = published.json()
    path = f"{BASE}/nodes/{node['id']}"
    etag = client.get(path).headers["etag"]
    assert client.delete(path, headers={"If-Match": etag}).status_code == 204
    retry = client.post(begun["complete_url"])
    missing = client.get(f"{BASE}/nodes/{uuid4()}")
    assert retry.status_code == missing.status_code == 403
    assert retry.json() == missing.json()
    assert client.get(f"{BASE}/nodes/{root_id}/children").json() == {"nodes": []}
    inspected = client.get(f"{BASE}/uploads/{begun['id']}")
    assert inspected.status_code == 200
    assert inspected.json()["status"] == "completed"
    assert "node" not in inspected.json()


def test_cross_origin_responses_expose_allow_and_etag(
    filesystem_http: FilesystemHttp, published_file: dict[str, object],
) -> None:
    client = filesystem_http.client
    origin = filesystem_http.factories.settings.cors.origins[0]
    path = f"{BASE}/nodes/{published_file['id']}"
    for method in ("GET", "OPTIONS"):
        response = client.request(method, path, headers={"Origin": origin})
        assert response.status_code in (200, 204)
        assert response.headers["access-control-allow-origin"] == origin
        assert {"allow", "etag"} <= set(response.headers["access-control-expose-headers"].lower().split(", "))


def test_delete_openapi_has_implemented_contract(filesystem_http: FilesystemHttp) -> None:
    schema = filesystem_http.client.get("/api/me/openapi.json").json()
    path = schema["paths"]["/filesystem/nodes/{node_id}"]
    delete = path["delete"]
    assert "x-umbod-status" not in delete
    assert {"204", "403", "409", "412", "422", "428"} <= set(delete["responses"])
    assert "501" not in delete["responses"]
    assert "204" in path["options"]["responses"]
    conditional = next(p for p in delete["parameters"] if p["name"] == "If-Match")
    assert "quoted positive numeric" in conditional["description"]
    assert conditional["required"] is True
    assert conditional["schema"]["pattern"] == r'^"[1-9][0-9]{0,18}"$'
