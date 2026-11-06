import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support.connector_plugins import TestConnectorPlugin
from umbod.config import AppConfig
from umbod.rest.main import create_app


@pytest.fixture(autouse=True)
def server_root_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "persistent-route-acceptance-test-root")


def test_health_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_empty_deployment_file(tmp_path, monkeypatch)
    client = TestClient(create_app(
        settings=AppConfig(rest={"metrics_enabled": False}, connector_store={"type": "inmemory"}),
        connector_registrations=[],
    ))

    response = client.get("/system/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "umbod-api"}


def test_connector_configuration_round_trips_through_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_test_deployment_file(tmp_path, monkeypatch)
    client = TestClient(create_app(
        settings=AppConfig(
            rest={"metrics_enabled": False},
            connector_store={"type": "inmemory"},
            admin_authentication={"mode": "simulation", "simulated_admin": True},
        ),
        connector_registrations=[TestConnectorPlugin.registration()],
    ))

    response = client.put(
        "/api/admin/connectors/catalog/test/configuration",
        json={
            "configuration": {
                "instance_name": "Demo",
                "api_key": "test-key",
                "default_response": "Hello from test connector",
            }
        },
    )
    configuration_response = client.get("/api/admin/connectors/catalog/test/configuration")

    assert response.status_code == 200
    assert configuration_response.status_code == 200
    assert configuration_response.json()["configuration"]["instance_name"] == "Demo"


def _set_empty_deployment_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    deployment_file = tmp_path / "connectors.json"
    deployment_file.write_text(json.dumps({"connectors": []}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment_file))


def _set_test_deployment_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    deployment_file = tmp_path / "connectors.json"
    deployment_file.write_text(json.dumps({"connectors": [{"id": "test"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment_file))
