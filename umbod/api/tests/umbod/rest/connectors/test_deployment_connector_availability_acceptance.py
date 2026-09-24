import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ConfigDict, SecretStr
from umbod.proxies import Model

from umbod.core.connectors.native.deployment import JsonFileDeploymentConnectorAvailabilitySource
from umbod.rest.main import create_app


class DeploymentConnectorConfiguration(Model):
    model_config = ConfigDict(extra="forbid")

    endpoint: str
    api_token: SecretStr


def test_deployment_file_exposes_only_declared_installed_connectors_in_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment_file = _write_deployment_file(
        tmp_path,
        {"connectors": [{"id": "slack-read-only"}, {"id": "postgresql"}]},
    )
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment_file))

    client = TestClient(create_app(connector_registrations=_installed_connectors()))

    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert [connector["id"] for connector in response.json()["connectors"]] == [
        "slack-read-only",
        "postgresql",
    ]


def test_deployment_available_connector_uses_installed_plugin_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment_file = _write_deployment_file(
        tmp_path,
        {"connectors": [{"id": "slack-read-only"}]},
    )
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment_file))

    client = TestClient(create_app(connector_registrations=_installed_connectors()))

    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert response.json()["connectors"] == [
        {
            "id": "slack-read-only",
            "display_name": "Slack Read Only",
            "description": "Reads Slack channels and messages",
            "extension": {"source": "built-in"},
            "publication_status": "unconfigured",
            "available_actions": ["configure"],
        }
    ]


def test_empty_deployment_file_exposes_no_connectors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment_file = _write_deployment_file(tmp_path, {"connectors": []})
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment_file))

    client = TestClient(create_app(connector_registrations=_installed_connectors()))

    response = client.get("/admin/connectors/catalog")

    assert response.status_code == 200
    assert response.json() == {"connectors": []}


def test_missing_deployment_file_environment_variable_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", raising=False)

    with pytest.raises(ValueError) as error:
        create_app(connector_registrations=_installed_connectors())

    assert "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH" in str(error.value)
    assert "required" in str(error.value)


def test_deployment_file_path_that_does_not_exist_fails_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_file = tmp_path / "missing-connectors.json"
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(missing_file))

    with pytest.raises(ValueError) as error:
        create_app(connector_registrations=_installed_connectors())

    assert str(missing_file) in str(error.value)
    assert "could not be found" in str(error.value)


def test_invalid_deployment_json_fails_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment_file = tmp_path / "connectors.json"
    deployment_file.write_text("not json", encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment_file))

    with pytest.raises(ValueError) as error:
        create_app(connector_registrations=_installed_connectors())

    assert "connector availability declaration is invalid" in str(error.value)


def test_unknown_deployment_connector_id_fails_startup_with_available_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment_file = _write_deployment_file(
        tmp_path,
        {"connectors": [{"id": "unknown-crm"}]},
    )
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment_file))

    with pytest.raises(ValueError) as error:
        create_app(connector_registrations=_installed_connectors())

    message = str(error.value)
    assert "unknown-crm" in message
    assert "available connector ids" in message
    assert "slack-read-only" in message
    assert "postgresql" in message
    assert "rest-api" in message


def test_deployment_file_rejects_runtime_adapter_declaration(tmp_path: Path) -> None:
    deployment_file = _write_deployment_file(
        tmp_path,
        {"connectors": [{"id": "slack", "runtime": {"adapter": "slack_api"}}]},
    )

    with pytest.raises(ValueError) as error:
        JsonFileDeploymentConnectorAvailabilitySource(deployment_file).load()

    assert "unexpected fields: runtime" in str(error.value)


def test_connector_specific_configuration_data_in_deployment_file_fails_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment_file = _write_deployment_file(
        tmp_path,
        {"connectors": [{"id": "slack-read-only", "api_token": "secret"}]},
    )
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment_file))

    with pytest.raises(ValueError) as error:
        create_app(connector_registrations=_installed_connectors())

    assert "contains unsupported connector fields" in str(error.value)
    assert "api_token" in str(error.value)


def _write_deployment_file(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "connectors.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _installed_connectors() -> list[dict[str, object]]:
    return [
        {
            "id": "slack-read-only",
            "display_name": "Slack Read Only",
            "capability_description": "Access connector capabilities.",
            "description": "Reads Slack channels and messages",
            "extension": {"source": "built-in"},
            "configuration_schema": DeploymentConnectorConfiguration,
        },
        {
            "id": "postgresql",
            "display_name": "PostgreSQL",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to PostgreSQL databases",
            "extension": {"source": "built-in"},
            "configuration_schema": DeploymentConnectorConfiguration,
        },
        {
            "id": "rest-api",
            "display_name": "REST API",
            "capability_description": "Access connector capabilities.",
            "description": "Connects to REST API services",
            "extension": {"source": "user-supplied"},
            "configuration_schema": DeploymentConnectorConfiguration,
        },
    ]
