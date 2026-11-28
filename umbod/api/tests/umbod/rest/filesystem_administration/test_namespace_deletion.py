from collections.abc import Iterator
from uuid import uuid4

import pytest

from umbod.config import AdminAuthConfig, AppConfig
from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER
from umbod.core.filesystem.namespaces import CreateSharedNamespace, NamespaceGroupAccess, SharedNamespaceView
from umbod.infrastructure import create_filesystem_namespace_management
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.main import create_app

from ..filesystem.conftest import AcceptedTestVerifier, FilesystemHttp, _filesystem_client
from ..filesystem.test_content import upload_file
from .test_namespace_administration import PATH
from .test_namespace_administration import namespace_settings as namespace_settings

BASE = "/api/me/filesystem"
CURRENT = {"expected_revision": 1, "expected_root_revision": 1}


class LocalIssuerVerifier(AcceptedTestVerifier):
    def verify(self, token: str) -> JwtClaims:
        return JwtClaims(claims={**super().verify(token).claims, "iss": LOCAL_DEVELOPMENT_ISSUER})


@pytest.fixture
def namespace_http(namespace_settings: AppConfig, request: pytest.FixtureRequest) -> Iterator[FilesystemHttp]:
    settings = namespace_settings.model_copy(update={
        "admin_authentication": AdminAuthConfig(mode="simulation", simulated_admin=getattr(request, "param", True)),
        "oidc": namespace_settings.oidc.model_copy(update={"issuer_url": LOCAL_DEVELOPMENT_ISSUER}),
        "mcp": namespace_settings.mcp.model_copy(update={"auth_mode": "oidc", "permission_group_claim": "filesystem_groups"}),
    })
    with _filesystem_client(create_app(settings, [], user_verifier=LocalIssuerVerifier())) as http:
        yield http


def shared_for_user(http: FilesystemHttp, name: str, issuer: str = LOCAL_DEVELOPMENT_ISSUER) -> SharedNamespaceView:
    database = http.factories.persistence_runtime.database
    management = create_filesystem_namespace_management(database=database, issuer=issuer)
    return http.client.portal.call(management.create, CreateSharedNamespace(
        name=name, groups=[NamespaceGroupAccess(group_id="team", access="read_write")],
    ))


def test_admin_delete_removes_only_target_from_admin_and_rest_discovery(namespace_http: FilesystemHttp) -> None:
    client = namespace_http.client
    target = shared_for_user(namespace_http, "Unused")
    other = shared_for_user(namespace_http, "Other")
    before = {entry["id"] for entry in client.get(f"{BASE}/namespaces").json()["namespaces"]}
    assert {str(target.id), str(other.id)} <= before
    assert client.get(f"{BASE}/nodes/{target.root_node_id}").status_code == 200

    path = f"{PATH}/{target.id}"
    response = client.request("DELETE", path, json=CURRENT)

    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"
    repeated = client.request("DELETE", path, json=CURRENT)
    assert repeated.status_code == 404
    assert repeated.json()["detail"]["code"] == "filesystem_namespace_not_found"
    assert client.get(f"{BASE}/nodes/{target.root_node_id}").status_code == 403
    assert {entry["id"] for entry in client.get(f"{BASE}/namespaces").json()["namespaces"]} == before - {str(target.id)}
    assert {entry["id"] for entry in client.get(PATH).json()["namespaces"]} == {str(other.id)}


@pytest.mark.parametrize("namespace_http", [False], indirect=True)
def test_content_writer_is_not_authorized_to_delete_namespace(namespace_http: FilesystemHttp) -> None:
    client = namespace_http.client
    root = str(shared_for_user(namespace_http, "Team files").root_node_id)
    target = next(entry for entry in client.get(f"{BASE}/namespaces").json()["namespaces"] if entry["root_node_id"] == root)
    assert "write" in target["permissions"]
    response = client.request("DELETE", f"{PATH}/{target['id']}", json=CURRENT)
    assert response.status_code == 403
    assert client.get(f"{BASE}/nodes/{root}").status_code == 200


@pytest.mark.parametrize("target_kind,status,code", [
    ("unknown", 404, "filesystem_namespace_not_found"),
    ("personal", 404, "filesystem_namespace_not_found"),
    ("foreign", 503, "filesystem_policy_unavailable"),
])
def test_delete_checks_eligibility_and_issuer_before_revisions(
    namespace_http: FilesystemHttp, target_kind: str, status: int, code: str,
) -> None:
    client = namespace_http.client
    if target_kind == "unknown":
        target_id = str(uuid4())
    elif target_kind == "personal":
        target_id = next(entry["id"] for entry in client.get(f"{BASE}/namespaces").json()["namespaces"] if entry["kind"] == "personal")
    else:
        foreign = shared_for_user(namespace_http, "Foreign", issuer="foreign")
        target_id = str(foreign.id)
    response = client.request("DELETE", f"{PATH}/{target_id}", json={**CURRENT, "expected_revision": 99})
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    if target_kind == "personal":
        assert target_id in {entry["id"] for entry in client.get(f"{BASE}/namespaces").json()["namespaces"]}
    elif target_kind == "foreign":
        management = create_filesystem_namespace_management(database=namespace_http.factories.persistence_runtime.database, issuer="foreign")
        assert client.portal.call(management.list) == [foreign]


@pytest.mark.parametrize("body,status,code", [
    ({"expected_revision": 1}, 422, "filesystem_policy_invalid"),
    ({"expected_root_revision": 1}, 422, "filesystem_policy_invalid"),
    ({**CURRENT, "expected_root_revision": "1"}, 422, "filesystem_policy_invalid"),
    ({**CURRENT, "expected_revision": True}, 422, "filesystem_policy_invalid"),
    ({**CURRENT, "expected_revision": 0}, 422, "filesystem_policy_invalid"),
    ({**CURRENT, "expected_revision": 2}, 409, "filesystem_policy_stale"),
    ({**CURRENT, "expected_root_revision": 2}, 409, "filesystem_policy_stale"),
])
def test_delete_requires_both_current_positive_integer_revisions(
    namespace_http: FilesystemHttp, body: dict[str, object], status: int, code: str,
) -> None:
    client = namespace_http.client
    target = client.post(PATH, json={"name": "Unused", "groups": []}).json()
    response = client.request("DELETE", f"{PATH}/{target['id']}", json=body)
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert client.get(PATH).json() == {"namespaces": [target]}


@pytest.mark.parametrize("child_kind", ["directory", "file", "invisible"])
def test_stored_children_block_admin_deletion_even_without_content_access(
    namespace_http: FilesystemHttp, child_kind: str,
) -> None:
    client = namespace_http.client
    target = shared_for_user(namespace_http, "Team files")
    root_path = f"{BASE}/nodes/{target.root_node_id}"
    if child_kind == "directory":
        response = client.post(f"{root_path}/directories", json={"name": "empty", "metadata": {"content_type": {}, "attributes": {}}})
    else:
        response = upload_file(client, f"{root_path}/uploads", "empty", b"")
    assert response.status_code == 201
    child_path = f"{BASE}/nodes/{response.json()['id']}"
    headers = {"Authorization": "Bearer outsider"} if child_kind == "invisible" else {}
    if child_kind == "invisible":
        assert client.get(child_path, headers=headers).status_code == 403

    deleted = client.request("DELETE", f"{PATH}/{target.id}", json=CURRENT, headers=headers)

    assert deleted.status_code == 409
    assert deleted.json()["detail"]["code"] == "filesystem_namespace_not_empty"
    assert client.get(child_path).status_code == 200
    assert client.get(root_path).status_code == 200


def test_pending_upload_returns_distinct_blocker(namespace_http: FilesystemHttp) -> None:
    client = namespace_http.client
    target = shared_for_user(namespace_http, "Team files")
    uploads_path = f"{BASE}/nodes/{target.root_node_id}/uploads"
    created = client.post(uploads_path, json={"name": "pending", "size_bytes": 0, "metadata": {"content_type": {}, "attributes": {}}})
    assert created.status_code == 201

    deleted = client.request("DELETE", f"{PATH}/{target.id}", json=CURRENT)

    assert deleted.status_code == 409
    assert deleted.json()["detail"]["code"] == "filesystem_namespace_active_uploads"
    assert client.get(created.headers["location"]).status_code == 200
