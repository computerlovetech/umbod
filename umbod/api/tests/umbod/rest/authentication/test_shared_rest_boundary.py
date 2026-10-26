import json
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from umbod.config import AppConfig
from umbod.core.callers import CallerContext
from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError
from umbod.rest.authentication.deps import get_caller_context, get_verified_access_claims
from umbod.rest.main import create_app


@pytest.fixture
def local_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "rest.sqlite")},
        runtime={"profile": "local", "auth": "dev"},
        admin_authentication={
            "mode": "simulation", "environment": "development", "simulated_admin": True,
            "simulated_user_id": "test-user", "membership_claim": "groups", "required_membership": "admin",
        },
        mcp={"permission_group_claim": "groups"},
    )


def caller_probe(
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    claims: Annotated[JwtClaims, Depends(get_verified_access_claims)],
) -> dict[str, object]:
    return {"caller": caller.model_dump(mode="json"), "claims": claims.claims}


def install_probes(app: FastAPI) -> None:
    app.add_api_route("/api/probe", caller_probe)
    for route in app.routes:
        if isinstance(route, Mount) and route.path in ("/api/admin", "/api/me"):
            route.app.add_api_route("/probe", caller_probe)


@pytest.mark.parametrize("personal", [
    {"enabled": False}, {"enabled": True, "identity_namespace": ""},
])
def test_default_local_caller_is_identical_across_every_rest_area(
    local_settings: AppConfig, personal: dict[str, object],
) -> None:
    settings = local_settings.model_copy(update={
        "personal_connections": local_settings.personal_connections.model_copy(update=personal),
    })
    app = create_app(settings, [])
    install_probes(app)
    forged = json.dumps({"signature": "trusted", "claims": {
        "iss": "attacker", "sub": "mallory", "groups": ["injected"],
        "authentication": "upstream_verified",
    }})
    with TestClient(app) as client:
        observations = [client.get(path).json() for path in (
            "/api/admin/probe", "/api/me/probe", "/api/probe",
        )]
        assert observations[0] == observations[1] == observations[2]
        assert observations[0]["caller"] == {
            "authentication": "local_simulation",
            "subject": {"issuer": {"value": "urn:umbod:local"}, "subject": "test-user"},
        }
        assert observations[0]["claims"]["iss"] == "urn:umbod:local"
        assert observations[0]["claims"]["groups"] == ["admin"]
        assert client.get("/api/probe", headers={"Authorization": "Bearer " + forged}).json() == observations[0]


class CountingVerifier:
    def __init__(self, token: str) -> None:
        self.token = token
        self.calls: list[str] = []

    def verify(self, token: str) -> JwtClaims:
        self.calls.append(token)
        if token != self.token:
            raise JwtVerificationError()
        return JwtClaims(claims={"sub": self.token, "groups": ["admin"]})


def test_supplied_verifiers_are_independent_strict_and_called_once(local_settings: AppConfig) -> None:
    admin = CountingVerifier("administrator")
    user = CountingVerifier("user")
    app = create_app(local_settings, [], admin_verifier=admin, user_verifier=user)
    install_probes(app)
    with TestClient(app) as client:
        assert client.get("/api/admin/users").status_code == 401
        assert client.get("/api/me/probe").status_code == 401
        assert admin.calls == [""] and not user.calls
        admin.calls.clear()
        assert client.get("/api/admin/users", headers={"Authorization": "Bearer administrator"}).status_code == 200
        assert admin.calls == ["administrator"]
        response = client.get("/api/me/probe", headers={"Authorization": "Bearer user"})
        assert response.status_code == 200
        assert response.json()["caller"]["authentication"] == "deployment_authenticated"
        assert user.calls == ["user"]
        assert client.get("/api/probe").json()["claims"]["sub"] == "test-user"
        assert admin.calls == ["administrator"] and user.calls == ["user"]


@pytest.mark.parametrize("prefix", ["", "/gateway"])
def test_root_routes_and_mounted_docs_require_authentication_with_deployment_prefix(
    local_settings: AppConfig, prefix: str,
) -> None:
    settings = local_settings.model_copy(update={
        "admin_authentication": local_settings.admin_authentication.model_copy(update={"mode": "jwt"}),
    })
    app = create_app(settings, [])
    install_probes(app)
    token = json.dumps({"signature": "trusted", "claims": {"sub": "alice", "groups": ["admin"]}})
    with TestClient(app, root_path=prefix) as client:
        for path in ("/api/probe", "/api/admin/docs", "/api/me/openapi.json"):
            denied = client.get(prefix + path)
            assert denied.status_code == 401
            assert denied.headers["cache-control"] == "no-store"
            assert client.get(prefix + path, headers={"Authorization": "Bearer " + token}).status_code == 200
        assert client.get(prefix + "/api/system/health").status_code == 200
        assert client.get(prefix + "/system/health").status_code == 200
        assert client.get(prefix + "/admin/users").status_code == 404


@pytest.mark.parametrize("path", [
    "/api/system/health/evil", "/api/oauth/downstream-mcp/callbackevil",
    "/api/oauth/downstream-mcp/other", "/api/new-feature",
])
def test_public_exemptions_do_not_include_similar_paths(local_settings: AppConfig, path: str) -> None:
    settings = local_settings.model_copy(update={
        "admin_authentication": local_settings.admin_authentication.model_copy(update={"mode": "jwt"}),
    })
    with TestClient(create_app(settings, [])) as client:
        assert client.get(path).status_code == 401


@pytest.mark.parametrize("runtime,authentication", [
    ({"profile": "local", "auth": "none"}, {}),
    ({"profile": "local", "auth": "dev"}, {"simulated_user_id": " "}),
])
def test_simulation_is_not_accepted_without_every_local_condition(
    local_settings: AppConfig, runtime: dict[str, str], authentication: dict[str, str],
) -> None:
    settings = local_settings.model_copy(update={
        "runtime": local_settings.runtime.model_copy(update=runtime),
        "admin_authentication": local_settings.admin_authentication.model_copy(update=authentication),
    })
    app = create_app(settings, [])
    install_probes(app)
    with TestClient(app) as client:
        for path in ("/api/probe", "/api/admin/users", "/api/me/probe"):
            assert client.get(path).status_code == 401
            assert client.get(path, headers={"Authorization": "Bearer forged"}).status_code == 401


@pytest.mark.parametrize("path", ["/api/probe", "/api/admin/users", "/api/me/catalogue"])
def test_root_cookie_safeguard_precedes_authentication(local_settings: AppConfig, path: str) -> None:
    settings = local_settings.model_copy(update={
        "admin_authentication": local_settings.admin_authentication.model_copy(update={"mode": "jwt"}),
    })
    with TestClient(create_app(settings, [])) as client:
        response = client.post(path, headers={"Cookie": "gateway=session"})
        assert response.status_code == 403
        assert response.headers["cache-control"] == "no-store"
        assert client.post(path).status_code == 401


def test_preflight_remains_public_but_actual_calls_require_credentials(local_settings: AppConfig) -> None:
    settings = local_settings.model_copy(update={
        "admin_authentication": local_settings.admin_authentication.model_copy(update={"mode": "jwt"}),
        "cors": local_settings.cors.model_copy(update={"origins": ["https://spa.example.com"]}),
    })
    with TestClient(create_app(settings, [])) as client:
        preflight = client.options("/api/new-feature", headers={
            "Origin": "https://spa.example.com", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,X-Umbod-Web-Request",
        })
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "https://spa.example.com"
        assert "access-control-allow-credentials" not in preflight.headers
        actual = client.post("/api/new-feature", headers={"Origin": "https://spa.example.com"})
        assert actual.status_code == 401
        assert actual.headers["access-control-allow-origin"] == "https://spa.example.com"


def test_disabled_admin_mode_does_not_disable_user_authentication_hooks(local_settings: AppConfig) -> None:
    settings = local_settings.model_copy(update={
        "admin_authentication": local_settings.admin_authentication.model_copy(update={"mode": "disabled"}),
    })
    user = CountingVerifier("user")
    app = create_app(settings, [], user_verifier=user)
    install_probes(app)
    with TestClient(app) as client:
        assert client.get("/api/me/docs").status_code == 401
        assert client.get("/api/probe").status_code == 401
        assert client.get("/api/me/probe", headers={"Authorization": "Bearer user"}).status_code == 200
        assert user.calls == ["user"]


def test_explicit_disabled_mode_keeps_administration_unguarded(local_settings: AppConfig) -> None:
    settings = local_settings.model_copy(update={
        "admin_authentication": local_settings.admin_authentication.model_copy(update={"mode": "disabled"}),
    })
    with TestClient(create_app(settings, [])) as client:
        assert client.get("/api/admin/docs").status_code == 200
        assert client.get("/api/admin/mcp-permissions/groups").status_code == 200
