from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.config import AppConfig
from umbod.rest.main import create_app


@pytest.mark.parametrize("profile,auth,environment,expected", [
    ("local", "dev", "development", 200),
    ("local", "oidc", "development", 401),
])
def test_tokenless_catalogue_simulation_is_limited_to_local_development(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    profile: str, auth: str, environment: str, expected: int,
) -> None:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        runtime={"profile": profile, "auth": auth},
        rest={"metrics_enabled": False},
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "auth.sqlite")},
        admin_authentication={"mode": "simulation", "environment": environment},
        personal_connections={"enabled": False},
    )
    with TestClient(create_app(settings, [])) as client:
        response = client.get("/api/me/catalogue")
        assert response.status_code == expected
        assert response.headers["cache-control"] == "no-store"
