from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbod.core.connectors.downstream_mcp.connection import DownstreamMcpConnectionConfiguration
from umbod.core.connectors.downstream_mcp.probe import DownstreamMcpProbe, ProbeResult
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_connector_probe
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


class ForbiddenProbe:
    async def probe(self, configuration: DownstreamMcpConnectionConfiguration) -> ProbeResult:
        raise AssertionError("Personal creation must not probe")


@pytest.fixture
def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> TestClient:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = APISettings(
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "api.sqlite3")},
        admin_authentication={"mode": "simulation", "simulated_admin": True},
        personal_connections={
            "enabled": getattr(request, "param", True), "identity_namespace": "test:catalogue"
        },
    )
    app = create_app(settings=settings, connector_registrations=[])
    admin = cast(FastAPI, next(route.app for route in app.routes if route.path == "/api/admin"))

    def probe() -> DownstreamMcpProbe:
        return ForbiddenProbe()

    admin.dependency_overrides[get_downstream_connector_probe] = probe
    return TestClient(app)


def payload() -> dict[str, Any]:
    return {
        "metadata": {
            "display_name": "Personal",
            "capability_description": "Personal connector capabilities",
            "public_path": "/mcp/proxies/personal",
        },
        "configuration": {"endpoint_url": "https://personal.example/mcp"},
    }


def test_creation_without_probe_returns_unpublished_unknown_and_no_credentials(client: TestClient) -> None:
    response = client.post("/api/admin/connectors/mcp/personal-oauth", json=payload())
    assert response.status_code == 201
    body = response.json()
    assert body["authorization_mode"] == "personal"
    assert body["auth_mode"] == "oauth"
    assert body["credential_configured"] is False
    assert body["publication_status"] == "unpublished"
    assert body["health"]["status"] == "unknown"
    assert client.get(f'/api/admin/connectors/mcp/{body["connector_id"]}/tools').json()["tools"] == []
    assert client.get("/api/admin/connectors/mcp").json()["connectors"][0]["authorization_mode"] == "personal"


@pytest.mark.parametrize("client", [False], indirect=True)
def test_disabled_policy_prevents_creation_without_writes(client: TestClient) -> None:
    response = client.post("/api/admin/connectors/mcp/personal-oauth", json=payload())
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "personal_connections_unavailable"}}
    assert client.get("/api/admin/connectors/mcp").json() == {"connectors": []}


def test_duplicate_path_is_rejected_without_second_definition(client: TestClient) -> None:
    assert client.post("/api/admin/connectors/mcp/personal-oauth", json=payload()).status_code == 201
    assert client.post("/api/admin/connectors/mcp/personal-oauth", json=payload()).status_code == 409
    assert len(client.get("/api/admin/connectors/mcp").json()["connectors"]) == 1


@pytest.mark.parametrize("section,field", [("configuration", "authorization"), ("configuration", "bearer_token"), ("metadata", "owner_id"), ("configuration", "authorization_mode")])
def test_credentials_and_ownership_fields_are_rejected(
    client: TestClient, section: str, field: str
) -> None:
    request = payload()
    request[section][field] = "secret"
    assert client.post("/api/admin/connectors/mcp/personal-oauth", json=request).status_code == 422
    assert client.get("/api/admin/connectors/mcp").json() == {"connectors": []}


def test_publication_allows_group_connector_assignment_without_capabilities(client: TestClient) -> None:
    connector_id = client.post("/api/admin/connectors/mcp/personal-oauth", json=payload()).json()["connector_id"]
    target_url = "/api/admin/mcp-permissions/assignable-targets"
    assert client.get(target_url).json() == {"connectors": [], "capabilities": []}
    assert client.put(f"/api/admin/connectors/mcp/{connector_id}/publication").status_code == 200
    assert client.get(target_url).json() == {
        "connectors": [{"connector_id": connector_id, "display_name": "Personal"}],
        "capabilities": [],
    }
    assert client.post("/api/admin/mcp-permissions/groups/team").status_code == 200
    assigned = client.put("/api/admin/mcp-permissions/groups/team/permissions", json={
        "connectors": [{"connector_id": connector_id, "permission_status": "enabled"}],
    })
    assert assigned.status_code == 200
    assert client.get("/api/admin/mcp-permissions/groups/team").json()["connector_ids"] == [connector_id]
    assert client.delete(f"/api/admin/connectors/mcp/{connector_id}/publication").status_code == 200
    assert client.get(target_url).json() == {"connectors": [], "capabilities": []}


def test_unsupported_edits_retain_definition_and_configuration(client: TestClient) -> None:
    created = client.post("/api/admin/connectors/mcp/personal-oauth", json=payload()).json()
    url = f'/api/admin/connectors/mcp/{created["connector_id"]}'
    assert client.patch(url, json={"display_name": "Changed"}).status_code == 422
    assert client.put(url + "/configuration", json={"auth_mode": "none", "endpoint_url": "https://changed.example/mcp"}).status_code == 422
    assert client.get(url).json() == created
    assert client.delete(url).status_code == 204
