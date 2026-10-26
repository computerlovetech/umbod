import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.config import AppConfig
from umbod.rest.main import create_app


def test_native_catalogue_requires_configuration_publication_activation_and_explicit_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "deployment.json"
    path.write_text(json.dumps({"connectors": [{"id": "test"}]}))
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(path))
    settings = AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "catalogue.sqlite")},
        admin_authentication={"mode": "simulation", "simulated_admin": True},
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/me/catalogue").json()["connectors"] == []
        client.put("/api/admin/connectors/catalog/test/configuration", json={"configuration": {
            "instance_name": "Demo", "api_key": "test-key",
            "default_response": "hello",
        }}).raise_for_status()
        client.put("/api/admin/connectors/catalog/test/publication").raise_for_status()
        client.put("/api/admin/connectors/catalog/test/tools/activation", json={"tools": [{
            "tool_id": "echo", "activation_status": "enabled",
        }]}).raise_for_status()
        assert client.get("/api/me/catalogue").json()["connectors"] == []
        client.put("/api/admin/mcp-permissions/groups/umbod-admins/permissions", json={"capabilities": [{
            "connector_id": "test", "capability_kind": "tool", "capability_key": "echo",
            "permission_status": "enabled",
        }]}).raise_for_status()
        response = client.get("/api/me/catalogue")
        assert response.status_code == 200
        connector = response.json()["connectors"][0]
        assert connector["kind"] == "native"
        assert connector["ownership"] == "shared"
        assert [tool["key"] for tool in connector["capabilities"]] == ["echo"]
        assert "test-key" not in response.text
        assert "api_key" not in response.text
        tool = connector["capabilities"][0]
        assert set(tool) == {"kind", "key", "name", "description", "input_schema", "output_schema"}
        assert tool["input_schema"]["properties"]["message"]["type"] == "string"
        assert tool["input_schema"]["required"] == ["message"]
        assert "configuration" not in tool["input_schema"]["properties"]
        assert tool["output_schema"] == {"status": "absent"}
        client.delete("/api/admin/connectors/catalog/test/publication").raise_for_status()
        assert client.get("/api/me/catalogue").json()["connectors"] == []
