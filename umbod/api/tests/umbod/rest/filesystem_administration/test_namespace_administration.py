from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from umbod.config import AdminAuthConfig, AppConfig
from umbod.rest.main import create_app


PATH = "/api/admin/filesystem/namespaces"


@pytest.fixture
def namespace_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(rest={"metrics_enabled": False}, connector_store={"type": "inmemory"}, admin_authentication={"mode": "simulation", "simulated_admin": True})


@pytest.fixture
def namespace_client(namespace_settings: AppConfig) -> Iterator[TestClient]:
    with TestClient(create_app(namespace_settings, []), raise_server_exceptions=False) as client:
        yield client


def test_namespace_management_uses_real_admin_mount_with_optimistic_replacement(namespace_client: TestClient) -> None:
    client = namespace_client
    assert client.get(PATH).json() == {"namespaces": []}
    assert client.post("/api/admin/groups", json={"group_id": "team"}).status_code == 204
    created = client.post(PATH, json={"name": "Shared", "groups": [{"group_id": "team", "access": "read_write"}]})
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    view = created.json()
    assert set(view) == {"id", "root_node_id", "name", "revision", "groups", "description", "root_revision"}
    assert view["revision"] == 1
    path = PATH + "/" + view["id"]
    command = {"expected_revision": 1, "name": "Renamed", "groups": []}
    saved = client.put(path, json=command)
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2 and saved.json()["groups"] == []
    assert client.put(path, json=command).status_code == 409
    assert client.get(PATH).json() == {"namespaces": [saved.json()]}
    assert client.get(PATH).headers["cache-control"] == "no-store"
    visible = client.get("/api/me/filesystem/namespaces")
    assert visible.status_code == 200
    assert [entry["kind"] for entry in visible.json()["namespaces"]] == ["personal"]
    assert client.get("/api/me/filesystem/browse", params={"node_id": view["root_node_id"]}).status_code == 403


def test_namespace_exists_independently_of_groups_and_supports_multiple_group_assignments(namespace_client: TestClient) -> None:
    created = namespace_client.post(PATH, json={"name": "Independent", "groups": []})
    assert created.status_code == 201
    original = created.json()
    assert original["groups"] == []
    for group_id in ("readers", "writers"):
        assert namespace_client.post("/api/admin/groups", json={"group_id": group_id}).status_code == 204
    grants = [{"group_id": "readers", "access": "read"}, {"group_id": "writers", "access": "read_write"}]
    assigned = namespace_client.put(PATH + "/" + original["id"], json={
        "expected_revision": original["revision"], "name": original["name"], "groups": grants,
    })
    assert assigned.status_code == 200
    saved = assigned.json()
    assert saved["id"] == original["id"]
    assert saved["root_node_id"] == original["root_node_id"]
    assert saved["groups"] == grants
    assert namespace_client.get(PATH).json() == {"namespaces": [saved]}
    revoked = namespace_client.put(PATH + "/" + saved["id"], json={
        "expected_revision": saved["revision"], "name": saved["name"], "groups": [],
    })
    assert revoked.status_code == 200
    assert revoked.json()["groups"] == []
    assert namespace_client.get(PATH).json() == {"namespaces": [revoked.json()]}


@pytest.mark.parametrize("body", [
    {}, {"name": "Shared"}, {"groups": []}, {"name": " ", "groups": []},
    {"name": "../unsafe", "groups": []}, {"name": "x" * 256, "groups": []},
    {"name": "Shared", "groups": [], "issuer": "client"},
    {"name": "Shared", "groups": [], "owner": "admin"},
    {"name": "Shared", "groups": [{"group_id": "unknown", "access": "read"}]},
    {"name": "Shared", "groups": [{"group_id": "unknown", "access": "write"}]},
    {"name": "Shared", "groups": [{"group_id": "unknown", "access": "read"}, {"group_id": "unknown", "access": "read_write"}]},
])
def test_invalid_namespace_commands_are_rejected_without_state_mutation(namespace_client: TestClient, body: dict[str, object]) -> None:
    response = namespace_client.post(PATH, json=body)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert namespace_client.get(PATH).json() == {"namespaces": []}


@pytest.mark.parametrize("revision", [0, -1, True, "1", 1.5, None])
def test_revision_must_be_required_positive_integer(namespace_client: TestClient, revision: object) -> None:
    view = namespace_client.post(PATH, json={"name": "Shared", "groups": []}).json()
    response = namespace_client.put(PATH + "/" + view["id"], json={"name": "Shared", "groups": [], "expected_revision": revision})
    assert response.status_code == 422
    assert namespace_client.get(PATH).json() == {"namespaces": [view]}


def test_description_create_edit_clear_and_omitted_save(namespace_client: TestClient) -> None:
    client = namespace_client
    created = client.post(PATH, json={"name": "Shared", "description": "Original", "groups": []})
    assert created.status_code == 201
    view = created.json()
    assert view["description"] == "Original" and view["root_revision"] >= 1
    path = PATH + "/" + view["id"]
    unchanged = client.put(path, json={"name": view["name"], "groups": [], "expected_revision": view["revision"]})
    assert unchanged.status_code == 200
    current = unchanged.json()
    assert current["description"] == "Original" and current["root_revision"] == view["root_revision"]
    changed = client.put(path, json={"name": "Renamed", "groups": [], "expected_revision": current["revision"], "description": "Edited", "expected_root_revision": current["root_revision"]})
    assert changed.status_code == 200
    current = changed.json()
    assert current["description"] == "Edited" and current["root_revision"] == view["root_revision"] + 1
    cleared = client.put(path, json={"name": current["name"], "groups": [], "expected_revision": current["revision"], "description": "", "expected_root_revision": current["root_revision"]})
    assert cleared.status_code == 200
    assert cleared.json()["description"] == ""
    assert client.get(PATH).json() == {"namespaces": [cleared.json()]}


@pytest.mark.parametrize("extra", [{}, {"expected_root_revision": None}, {"expected_root_revision": 0}, {"expected_root_revision": True}, {"expected_root_revision": "1"}])
def test_description_save_requires_positive_root_revision(namespace_client: TestClient, extra: dict[str, object]) -> None:
    view = namespace_client.post(PATH, json={"name": "Shared", "groups": []}).json()
    response = namespace_client.put(PATH + "/" + view["id"], json={"name": "Shared", "groups": [], "expected_revision": 1, "description": "", **extra})
    assert response.status_code == 422
    assert namespace_client.get(PATH).json() == {"namespaces": [view]}


def test_root_revision_without_description_is_rejected(namespace_client: TestClient) -> None:
    view = namespace_client.post(PATH, json={"name": "Shared", "groups": []}).json()
    response = namespace_client.put(PATH + "/" + view["id"], json={"name": "Shared", "groups": [], "expected_revision": 1, "expected_root_revision": view["root_revision"]})
    assert response.status_code == 422
    assert namespace_client.get(PATH).json() == {"namespaces": [view]}


def test_stale_description_root_revision_returns_conflict(namespace_client: TestClient) -> None:
    view = namespace_client.post(PATH, json={"name": "Shared", "groups": []}).json()
    response = namespace_client.put(PATH + "/" + view["id"], json={"name": "Changed", "groups": [], "expected_revision": 1, "description": "Stale", "expected_root_revision": view["root_revision"] + 1})
    assert response.status_code == 409
    assert namespace_client.get(PATH).json() == {"namespaces": [view]}


def test_duplicate_shared_name_is_conflict(namespace_client: TestClient) -> None:
    command = {"name": "Shared", "groups": []}
    assert namespace_client.post(PATH, json=command).status_code == 201
    assert namespace_client.post(PATH, json=command).status_code == 409


@pytest.mark.parametrize("authentication,status", [
    (AdminAuthConfig(mode="jwt"), 401),
    (AdminAuthConfig(mode="simulation", simulated_admin=False), 403),
])
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE"])
def test_namespace_administration_requires_admin_membership(
    namespace_settings: AppConfig, authentication: AdminAuthConfig, status: int, method: str,
) -> None:
    settings = namespace_settings.model_copy(update={"admin_authentication": authentication})
    with TestClient(create_app(settings, [])) as client:
        path = PATH + "/" + str(uuid4()) if method in {"PUT", "DELETE"} else PATH
        body = {"expected_revision": 1, "expected_root_revision": 1} if method == "DELETE" else {"name": "Shared", "groups": [], "expected_revision": 1}
        response = client.request(method, path, json=body)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"


def test_namespace_mutations_keep_cookie_csrf_protection(namespace_client: TestClient) -> None:
    command = {"name": "Shared", "groups": []}
    blocked = namespace_client.post(PATH, json=command, headers={"Cookie": "gateway=yes"})
    assert blocked.status_code == 403
    assert namespace_client.get(PATH).json() == {"namespaces": []}
    accepted = namespace_client.post(PATH, json=command, headers={
        "Cookie": "gateway=yes", "Origin": "http://localhost:3010", "X-Umbod-Web-Request": "1",
    })
    assert accepted.status_code == 201


def test_unknown_namespace_storage_failure_is_sanitized(namespace_client: TestClient) -> None:
    from fastapi import FastAPI
    from starlette.routing import Mount

    from umbod.rest.filesystem_administration.deps import get_policy_database

    app: FastAPI = next(route.app for route in namespace_client.app.routes if isinstance(route, Mount) and route.path == "/api/admin")

    def fail_database() -> None:
        raise RuntimeError("private storage credentials")

    app.dependency_overrides[get_policy_database] = fail_database
    response = namespace_client.get(PATH)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "filesystem_policy_storage_failure"
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text
