import json
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.routing import Mount

from umbod.core.connectors.openapi.importing import DefaultOpenApiImportPreparer, InMemoryOpenApiCandidateImporter
from umbod.core.connectors.openapi.management import OpenApiBearerConfiguration, OpenApiConfigurationPort, OpenApiConfigurationStatus, OpenApiConnectorManagementService
from umbod.core.connectors.openapi.management.models import CreateOpenApiConnector, ImportOpenApiCatalog, OpenApiConnector, OpenApiConnectorCatalog
from umbod.core.connectors.openapi.management.setup import OpenApiConnectorSetupService
from umbod.core.connectors.openapi.management.setup_ports import OpenApiConnectorSetupPort
from umbod.rest.connectors.openapi.dependencies import get_openapi_configuration_port, get_openapi_connector_management_service, get_openapi_connector_setup_port
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    availability = tmp_path / "availability.json"
    availability.write_text(json.dumps({"connectors": []}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability))
    return create_app(APISettings(rest={"metrics_port": 19589}, admin_authentication={"mode": "simulation", "simulated_admin": True}), [])


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as transport:
        yield transport


@pytest.fixture
def admin_app(app: FastAPI) -> FastAPI:
    return next(route.app for route in app.routes if isinstance(route, Mount) and route.path == "/api/admin")


@pytest.fixture
def payload() -> dict[str, object]:
    return {
        "display_name": "Example", "tool_name_prefix": "example_api", "capability_description": "Manage example resources",
        "document": {"openapi": "3.1.0", "info": {"title": "Example", "version": "1"}, "servers": [{"url": "https://api.example.com"}], "paths": {"/items": {"get": {"operationId": "listItems", "responses": {"200": {"description": "ok"}}}}}},
        "approved_hosts": ["api.example.com"], "authentication_type": "bearer", "bearer_token": "secret-token-not-for-errors",
    }


@pytest.mark.parametrize("authentication_type", ["none", "bearer"])
def test_setup_creates_imports_and_configures_connector(
    client: TestClient, payload: dict[str, object], authentication_type: str
) -> None:
    payload.update(authentication_type=authentication_type, bearer_token="token" if authentication_type == "bearer" else "")
    response = client.post("/api/admin/connectors/openapi/setup", json=payload)
    assert response.status_code == 201
    connector_id = response.json()["connector_id"]
    assert response.json()["display_name"] == "Example"
    assert response.json()["publication_status"] == "draft"
    tools = client.get(f"/api/admin/connectors/openapi/{connector_id}/tools")
    assert tools.json()["tools"][0]["operation_id"] == "listItems"
    configuration = client.get(f"/api/admin/connectors/openapi/{connector_id}/configuration")
    assert configuration.json()["authentication_type"] == authentication_type
    assert "token" not in response.text


@pytest.mark.parametrize("updates", [
    {"document": {}}, {"approved_hosts": ["attacker.example.com"]}, {"bearer_token": " "},
    {"display_name": " "}, {"tool_name_prefix": "invalid!"}, {"bearer_token": {"secret": "do-not-reflect"}},
])
def test_invalid_setup_leaves_no_connector_and_does_not_reflect_secrets(
    client: TestClient, payload: dict[str, object], updates: dict[str, object]
) -> None:
    payload.update(updates)
    response = client.post("/api/admin/connectors/openapi/setup", json=payload)
    assert response.status_code == 422
    assert "secret-token-not-for-errors" not in response.text
    assert "do-not-reflect" not in response.text
    assert client.get("/api/admin/connectors/openapi").json() == {"connectors": []}


class FailingConfiguration:
    def __init__(self, clear_fails: bool) -> None:
        self.tokens: dict[str, SecretStr] = {}
        self.clear_fails = clear_fails

    async def status(self, connector_id: str) -> OpenApiConfigurationStatus:
        configured = connector_id in self.tokens
        return OpenApiConfigurationStatus(configured=configured, authentication_type="bearer" if configured else "none")

    async def configure(self, connector_id: str, bearer_token: SecretStr) -> OpenApiConfigurationStatus:
        self.tokens[connector_id] = bearer_token
        raise RuntimeError("secret-token-not-for-errors")

    async def clear(self, connector_id: str) -> OpenApiConfigurationStatus:
        if self.clear_fails:
            raise RuntimeError("secret-token-not-for-errors")
        self.tokens.pop(connector_id, None)
        return OpenApiConfigurationStatus(configured=False, authentication_type="none")

    async def resolve(self, connector_id: str) -> OpenApiBearerConfiguration | None:
        token = self.tokens.get(connector_id)
        return OpenApiBearerConfiguration(bearer_token=token) if token is not None else None


class DeleteFailingManagement:
    def __init__(self, service: OpenApiConnectorManagementService) -> None:
        self.service = service

    async def create_connector(self, request: CreateOpenApiConnector) -> OpenApiConnector:
        return await self.service.create_connector(request)

    async def import_catalog(self, request: ImportOpenApiCatalog) -> OpenApiConnectorCatalog:
        return await self.service.import_catalog(request)

    async def get_connector(self, connector_id: str) -> OpenApiConnector:
        return await self.service.get_connector(connector_id)

    async def delete_connector(self, connector_id: str) -> None:
        raise RuntimeError("secret-token-not-for-errors")


def test_configuration_failure_clears_credentials_and_deletes_connector(
    client: TestClient, admin_app: FastAPI, payload: dict[str, object]
) -> None:
    configuration = FailingConfiguration(False)

    def configuration_port() -> OpenApiConfigurationPort:
        return configuration

    admin_app.dependency_overrides[get_openapi_configuration_port] = configuration_port
    response = client.post("/api/admin/connectors/openapi/setup", json=payload)
    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "openapi_setup_failed"}}
    assert configuration.tokens == {}
    assert client.get("/api/admin/connectors/openapi").json() == {"connectors": []}


@pytest.mark.parametrize("failure", ["delete", "clear"])
def test_cleanup_failure_returns_connector_identifier_without_secrets(
    client: TestClient, admin_app: FastAPI, payload: dict[str, object], failure: str
) -> None:
    configuration = FailingConfiguration(failure == "clear")

    def setup_port(management: Annotated[OpenApiConnectorManagementService, Depends(get_openapi_connector_management_service)]) -> OpenApiConnectorSetupPort:
        return OpenApiConnectorSetupService(DeleteFailingManagement(management) if failure == "delete" else management, InMemoryOpenApiCandidateImporter(), DefaultOpenApiImportPreparer(), configuration)

    admin_app.dependency_overrides[get_openapi_connector_setup_port] = setup_port
    response = client.post("/api/admin/connectors/openapi/setup", json=payload)
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "openapi_setup_cleanup_failed"
    assert detail["connector_id"]
    assert "secret-token-not-for-errors" not in response.text
    if failure == "delete":
        assert configuration.tokens == {}
        assert client.get(f"/api/admin/connectors/openapi/{detail['connector_id']}").status_code == 200
    else:
        assert client.get("/api/admin/connectors/openapi").json() == {"connectors": []}


@pytest.mark.parametrize("content_length", ["11000000", None])
def test_setup_rejects_oversized_body_without_persistence(
    client: TestClient, content_length: str | None
) -> None:
    headers = {"Content-Type": "application/json"}
    if content_length is not None:
        headers["Content-Length"] = content_length
    response = client.post("/api/admin/connectors/openapi/setup", content=iter([b" " * 11000000]), headers=headers)
    assert response.status_code == 413
    assert client.get("/api/admin/connectors/openapi").json() == {"connectors": []}
