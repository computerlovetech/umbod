from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from umbod.config.app import AppConfig
from umbod.core.connectors.downstream_mcp.personal_connections.development_identity import local_personal_identity_enabled
from umbod.core.connectors.downstream_mcp.personal_connections.principal import canonical_principal
from umbod.core.connectors.downstream_mcp.personal_connections.identity_models import ResolvedPersonalIdentity
from umbod.core.connectors.downstream_mcp.adapters.identity import personal_identity_facts
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
from umbod.hosting import JwtClaims, create_rest_app
from umbod.rest.authentication.deps import VERIFIED_ACCESS_CLAIMS_STATE_KEY


class AcceptingVerifier:
    def verify(self, token: str) -> JwtClaims:
        return JwtClaims(claims={"sub": "external-owner", "groups": ["external"]})


@pytest.fixture
def local_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        rest={"metrics_enabled": False},
        admin_authentication={
            "simulated_user_id": "configured-stable-owner",
            "simulated_user_email": "test@example.org",
            "simulated_user_name": "Configured Test User",
            "membership_claim": "custom-groups",
            "required_membership": "configured-administrators",
        },
        personal_connections={"enabled": True, "identity_namespace": "test:configured"},
    )


@pytest.fixture
def local_client(local_settings: AppConfig) -> Iterator[TestClient]:
    app = create_rest_app(local_settings, connector_registrations=[], admin_verifier=None, oauth_service=None)
    personal_app = next(route.app for route in app.routes if getattr(route, "path", "") == "/api/me")

    @personal_app.get("/identity")
    def identity(request: Request) -> dict[str, object]:
        verified: JwtClaims = getattr(request.state, VERIFIED_ACCESS_CLAIMS_STATE_KEY)
        resolution = canonical_principal(personal_identity_policy_from_app_config(local_settings), personal_identity_facts(verified.claims))
        assert isinstance(resolution, ResolvedPersonalIdentity)
        principal = resolution.principal
        return {"claims": verified.claims, "owner": principal.subject, "namespace": principal.namespace}

    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer attacker-controlled-token"},
    {"X-Auth-Request-User": "attacker", "X-Auth-Request-Email": "attacker@example.org", "X-Auth-Request-Groups": "external", "sub": "attacker", "groups": "external"},
])
def test_local_personal_api_uses_configured_identity_only(local_client: TestClient, headers: dict[str, str]) -> None:
    assert local_client.get("/api/me/connectors/mcp", headers=headers).json() == {"connectors": []}
    response = local_client.get("/api/me/identity", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "owner": "configured-stable-owner", "namespace": "test:configured",
        "claims": {"iss": "urn:umbod:local", "sub": "configured-stable-owner", "email": "test@example.org", "name": "Configured Test User", "custom-groups": ["configured-administrators"]},
    }
    admin = local_client.get("/api/admin/users")
    assert admin.status_code == 200
    assert admin.json()["id"] == "configured-stable-owner"


def test_supplied_personal_verifier_remains_strict_for_missing_token(local_settings: AppConfig) -> None:
    app = create_rest_app(local_settings, connector_registrations=[], admin_verifier=None, oauth_service=None, user_verifier=AcceptingVerifier())
    with TestClient(app) as client:
        assert client.get("/api/me/connectors/mcp").status_code == 401


def test_supplied_admin_verifier_does_not_control_local_personal_identity(local_settings: AppConfig) -> None:
    app = create_rest_app(local_settings, connector_registrations=[], admin_verifier=AcceptingVerifier(), oauth_service=None)
    with TestClient(app) as client:
        assert client.get("/api/me/connectors/mcp").status_code == 200
        assert client.get("/api/admin/users").status_code == 403


@pytest.mark.parametrize("section,updates", [
    ("runtime", {"auth": "google"}),
    ("runtime", {"auth": "none"}),
    ("admin_authentication", {"mode": "jwt"}),
    ("admin_authentication", {"mode": "disabled"}),
    ("admin_authentication", {"simulated_user_id": " "}),
    ("personal_connections", {"enabled": False}),
    ("personal_connections", {"identity_namespace": "test:"}),
    ("personal_connections", {"identity_namespace": " test:authority"}),
    ("personal_connections", {"identity_namespace": "test:authority "}),
    ("personal_connections", {"identity_namespace": "authority"}),
])
def test_local_identity_policy_fails_closed(local_settings: AppConfig, section: str, updates: dict[str, object]) -> None:
    settings = local_settings.model_copy(update={section: getattr(local_settings, section).model_copy(update=updates)})
    assert not local_personal_identity_enabled(personal_identity_policy_from_app_config(settings))
    app = create_rest_app(settings, connector_registrations=[], admin_verifier=None, oauth_service=None)
    with TestClient(app) as client:
        expected_status = (
            403 if section == "personal_connections" and settings.personal_connections.enabled
            else 401 if settings.personal_connections.enabled else 404
        )
        assert client.get("/api/me/connectors/mcp").status_code == expected_status


def test_development_jwt_mode_requires_token(local_settings: AppConfig) -> None:
    settings = local_settings.model_copy(update={"admin_authentication": local_settings.admin_authentication.model_copy(update={"mode": "jwt"})})
    app = create_rest_app(settings, connector_registrations=[], admin_verifier=None, oauth_service=None)
    with TestClient(app) as client:
        assert client.get("/api/me/connectors/mcp").status_code == 401
