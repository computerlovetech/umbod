import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app


def test_health_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_empty_deployment_file(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.get("/system/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "umbod-api"}


def test_connector_configuration_round_trips_through_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_test_deployment_file(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.put(
        "/admin/connectors/catalog/test/configuration",
        json={
            "configuration": {
                "instance_name": "Demo",
                "api_key": "test-key",
                "default_response": "Hello from test connector",
            }
        },
    )
    configuration_response = client.get("/admin/connectors/catalog/test/configuration")

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
