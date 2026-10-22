import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.hosting import AppConfig, JwtClaims, JwtVerificationError, create_rest_app


class AdminVerifier:
    def verify(self, token: str) -> JwtClaims:
        if token != "administrator-token":
            raise JwtVerificationError("Invalid token")
        return JwtClaims(claims={"sub": "administrator", "groups": ["owners"]})


class PersonalVerifier:
    def verify(self, token: str) -> JwtClaims:
        if token != "personal-token":
            raise JwtVerificationError("Invalid token")
        return JwtClaims(claims={"sub": "alice", "groups": []})


@pytest.mark.parametrize("supplied_user_verifier", [False, True])
def test_admin_verifier_is_never_inherited_by_personal_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, supplied_user_verifier: bool,
) -> None:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        rest={"metrics_enabled": False},
        admin_authentication={"mode": "jwt", "required_membership": "owners"},
        personal_connections={"enabled": True, "identity_namespace": "test:hosting"},
    )
    app = create_rest_app(
        settings, connector_registrations=[], admin_verifier=AdminVerifier(), oauth_service=None,
        user_verifier=PersonalVerifier() if supplied_user_verifier else None,
    )
    personal_token = "personal-token" if supplied_user_verifier else json.dumps({
        "signature": "trusted", "claims": {"sub": "alice", "groups": []},
    })
    with TestClient(app) as client:
        assert client.get("/api/me/connectors/mcp").status_code == 401
        assert client.get("/api/admin/users", headers={"Authorization": "Bearer administrator-token"}).status_code == 200
        assert client.get("/api/me/connectors/mcp", headers={"Authorization": "Bearer administrator-token"}).status_code == 401
        assert client.get("/api/me/connectors/mcp", headers={"Authorization": "Bearer " + personal_token}).json() == {"connectors": []}
        assert client.get("/api/admin/users", headers={"Authorization": "Bearer " + personal_token}).status_code == 401


def test_personal_authentication_hook_rejects_unknown_keywords() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument 'user_verify'"):
        create_rest_app(
            AppConfig(), connector_registrations=[], admin_verifier=None, oauth_service=None,
            user_verify=PersonalVerifier(),
        )


def test_personal_api_is_not_mounted_without_explicit_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    app = create_rest_app(
        AppConfig(rest={"metrics_enabled": False}), connector_registrations=[],
        admin_verifier=AdminVerifier(), oauth_service=None, user_verifier=PersonalVerifier(),
    )
    with TestClient(app) as client:
        assert client.get("/api/me/connectors/mcp", headers={"Authorization": "Bearer personal-token"}).status_code == 404
