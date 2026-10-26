from collections.abc import Iterator
from pathlib import Path
from unittest.mock import create_autospec

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from umbod.config import AdminAuthConfig, AppConfig
from umbod.core.filesystem.administration import PolicyConflict, RootGroupPolicyManagement
from umbod.core.persistence import Database
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.filesystem_administration.deps import get_policy_database, get_root_group_policy_management
from umbod.rest.filesystem_administration import deps
from umbod.rest.main import create_app

PATH = "/api/admin/filesystem/root-access"


@pytest.fixture
def admin_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "administration.sqlite")},
        admin_authentication={"mode": "simulation", "simulated_admin": True},
        oidc={"issuer_url": " Exact Issuer "},
        mcp={"permission_group_claim": "filesystem_groups"},
    )


@pytest.fixture
def admin_client(admin_settings: AppConfig) -> Iterator[TestClient]:
    with TestClient(create_app(admin_settings, []), raise_server_exceptions=False) as client:
        yield client


def admin_app(client: TestClient) -> FastAPI:
    return next(route.app for route in client.app.routes if isinstance(route, Mount) and route.path == "/api/admin")


def test_authenticated_admin_can_initialize_edit_revoke_and_detect_stale(admin_client: TestClient) -> None:
    initial = admin_client.get(PATH)
    assert initial.status_code == 200
    assert initial.headers["cache-control"] == "no-store"
    assert initial.json()["status"] == "uninitialized"
    assert initial.json()["suggested_issuer"] == "urn:umbod:local"
    assert initial.json()["group_claim"] == "filesystem_groups"
    groups = [{"issuer": " Future Issuer ", "group_id": " Team ", "permissions": ["write"]}]
    saved = admin_client.put(PATH, json={"expected_revision": initial.json()["revision"], "groups": groups})
    assert saved.status_code == 200
    assert saved.json()["groups"] == groups
    assert saved.json()["status"] == "ready"
    assert saved.headers["cache-control"] == "no-store"
    revoked = admin_client.put(PATH, json={"expected_revision": saved.json()["revision"], "groups": []})
    assert revoked.status_code == 200
    assert revoked.json()["groups"] == []
    stale = admin_client.put(PATH, json={"expected_revision": saved.json()["revision"], "groups": groups})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "filesystem_policy_stale"
    assert stale.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("payload", [
    {"groups": []}, {"expected_revision": "r"},
    {"expected_revision": "r", "groups": [], "caller": "admin"},
    {"expected_revision": "r", "groups": [{"issuer": " ", "group_id": "g", "permissions": ["read"]}]},
    {"expected_revision": "r", "groups": [{"issuer": "i", "group_id": "g", "permissions": []}]},
])
def test_invalid_admin_policy_is_sanitized_and_no_store(admin_client: TestClient, payload: dict[str, object]) -> None:
    response = admin_client.put(PATH, json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "filesystem_policy_invalid"
    assert response.headers["cache-control"] == "no-store"
    assert "input" not in response.text


@pytest.mark.parametrize("authentication,status", [
    (AdminAuthConfig(mode="jwt"), 401),
    (AdminAuthConfig(mode="simulation", simulated_admin=False), 403),
])
@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_admin_authentication_and_membership_remain_required(admin_settings: AppConfig, authentication: AdminAuthConfig, status: int, method: str) -> None:
    settings = admin_settings.model_copy(update={"admin_authentication": authentication})
    with TestClient(create_app(settings, [])) as client:
        response = client.request(method, PATH, json={"expected_revision": "r", "groups": []})
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"


def test_cookie_csrf_applies_before_mutations(admin_client: TestClient) -> None:
    initial = admin_client.get(PATH).json()
    payload = {"expected_revision": initial["revision"], "groups": []}
    blocked = admin_client.put(PATH, json=payload, headers={"Cookie": "gateway=yes"})
    assert blocked.status_code == 403
    assert blocked.headers["cache-control"] == "no-store"
    assert admin_client.get(PATH).json() == initial
    accepted = admin_client.put(PATH, json=payload, headers={
        "Cookie": "gateway=yes", "Origin": "http://localhost:3010", "X-Umbod-Web-Request": "1",
    })
    assert accepted.status_code == 200


@pytest.mark.parametrize("failure", ["readiness", "factory", "inspect", "save", "response"])
def test_unknown_failures_are_safe_with_actual_app_boundary(admin_client: TestClient, failure: str, monkeypatch: pytest.MonkeyPatch) -> None:
    app = admin_app(admin_client)

    def fail() -> None:
        raise RuntimeError("private database credentials")

    service = create_autospec(RootGroupPolicyManagement, instance=True)
    if failure == "readiness":
        app.dependency_overrides[get_policy_database] = fail
    elif failure == "factory":
        monkeypatch.setattr(deps, "create_root_group_policy_management", fail)
    else:
        if failure == "response":
            service.inspect.return_value = object()
        else:
            service.inspect.side_effect = RuntimeError("private database credentials")
            service.save.side_effect = RuntimeError("private database credentials")
        def provide_management() -> RootGroupPolicyManagement:
            return service

        app.dependency_overrides[get_root_group_policy_management] = provide_management
    response = (
        admin_client.put(PATH, json={"expected_revision": "r", "groups": []})
        if failure == "save" else admin_client.get(PATH)
    )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "filesystem_policy_storage_failure"
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text


def test_management_is_created_per_request_from_same_prepared_database(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    factory = deps.create_root_group_policy_management
    services: list[RootGroupPolicyManagement] = []
    databases: list[Database] = []

    def track(*, database: Database) -> RootGroupPolicyManagement:
        service = factory(database=database)
        services.append(service)
        databases.append(database)
        return service

    monkeypatch.setattr(deps, "create_root_group_policy_management", track)
    assert admin_client.get(PATH).status_code == 200
    assert admin_client.get(PATH).status_code == 200
    assert services[0] is not services[1]
    assert databases[0] is databases[1]


class FalseRoleVerifier:
    def verify(self, token: str) -> JwtClaims:
        return JwtClaims(claims={"iss": "token issuer", "sub": "user", "admin": True, "groups": ["not-admin"]})


def test_boolean_admin_role_is_not_membership(admin_settings: AppConfig) -> None:
    authentication = AdminAuthConfig(mode="jwt", membership_claim="groups", required_membership="admins")
    settings = admin_settings.model_copy(update={"admin_authentication": authentication})
    with TestClient(create_app(settings, [], admin_verifier=FalseRoleVerifier())) as client:
        response = client.get(PATH, headers={"Authorization": "Bearer user"})
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_known_conflict_errors_are_safe_and_no_store(admin_client: TestClient) -> None:
    service = create_autospec(RootGroupPolicyManagement, instance=True)
    service.save.side_effect = PolicyConflict("private policy")

    def provide_management() -> RootGroupPolicyManagement:
        return service

    admin_app(admin_client).dependency_overrides[get_root_group_policy_management] = provide_management
    response = admin_client.put(PATH, json={"expected_revision": "r", "groups": []})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "filesystem_policy_conflict"
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text


def test_production_authority_hint_preserves_configured_oidc_issuer(admin_settings: AppConfig) -> None:
    settings = admin_settings.model_copy(update={
        "runtime": admin_settings.runtime.model_copy(update={"profile": "production", "auth": "auth0"}),
        "admin_authentication": AdminAuthConfig(
            mode="jwt", environment="production", required_membership="not-admin",
            jwks_url="https://issuer.example/jwks",
        ),
        "oidc": admin_settings.oidc.model_copy(update={"audience": "api"}),
    })
    with TestClient(create_app(settings, [], admin_verifier=FalseRoleVerifier())) as client:
        response = client.get(PATH, headers={"Authorization": "Bearer accepted"})
        assert response.status_code == 200
        assert response.json()["suggested_issuer"] == " Exact Issuer "


def test_local_authority_hint_does_not_depend_on_oidc_configuration(admin_settings: AppConfig) -> None:
    settings = admin_settings.model_copy(update={"oidc": admin_settings.oidc.model_copy(update={"issuer_url": ""})})
    with TestClient(create_app(settings, [])) as client:
        initial = client.get(PATH).json()
        assert initial["suggested_issuer"] == "urn:umbod:local"
        response = client.put(PATH, json={"expected_revision": initial["revision"], "groups": [{"issuer": "future", "group_id": "team", "permissions": ["discover"]}]})
        assert response.status_code == 200
        assert client.get("/api/me/filesystem/root").status_code in (401, 403)
