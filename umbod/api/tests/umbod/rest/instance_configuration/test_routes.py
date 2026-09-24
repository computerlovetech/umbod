import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.config import AdminAuthConfig, AppConfig, RuntimeConfig
from umbod.rest.main import create_app


@pytest.fixture
def admin_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    _configure_connector_availability(tmp_path, monkeypatch)
    settings = AppConfig(
        runtime=RuntimeConfig(app_name="effective-instance"),
        admin_authentication=AdminAuthConfig(mode="simulation", simulated_admin=True),
    )
    with TestClient(create_app(settings=settings)) as client:
        yield client


def test_get_instance_configuration_returns_running_effective_config(
    admin_client: TestClient,
) -> None:
    response = admin_client.get("/admin/instance-configuration")

    assert response.status_code == 200
    entries = {
        entry["variable"]: entry
        for group in response.json()["groups"]
        for entry in group["entries"]
    }
    assert entries["UMBOD_APP_NAME"] == {
        "variable": "UMBOD_APP_NAME",
        "label": "Application name",
        "description": "Name used to identify this Umbod instance.",
        "type": "string",
        "value": "effective-instance",
    }


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_instance_configuration_has_no_mutation_route(
    admin_client: TestClient,
    method: str,
) -> None:
    response = admin_client.request(method, "/admin/instance-configuration")

    assert response.status_code == 405


@pytest.mark.parametrize(
    ("authentication", "expected_status"),
    [
        (AdminAuthConfig(mode="jwt"), 401),
        (AdminAuthConfig(mode="simulation", simulated_admin=False), 403),
    ],
)
def test_instance_configuration_uses_admin_authorization_policy(
    authentication: AdminAuthConfig,
    expected_status: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_connector_availability(tmp_path, monkeypatch)
    settings = AppConfig(admin_authentication=authentication)

    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/admin/instance-configuration")

    assert response.status_code == expected_status


def _configure_connector_availability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": []}), encoding="utf-8")
    monkeypatch.setenv(
        "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH",
        str(availability_path),
    )
