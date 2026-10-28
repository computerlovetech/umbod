import json

from fastapi.testclient import TestClient
from umbod.rest.main import create_app
from umbod.rest.settings import APISettings
from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService
from tests.umbod.core.downstream_mcp_connectors.adapters.oauth_fakes import MemoryDiscovery, ScriptedSessionFactory
from tests.umbod.core.downstream_mcp_connectors.adapters.test_oauth_service import (
    MemoryHost,
)


def test_shared_oauth_api_authentication_contract_and_redaction(monkeypatch, tmp_path):
    declaration = tmp_path / "connectors.json"
    declaration.write_text('{"connectors": []}')
    monkeypatch.setenv(
        "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(declaration)
    )
    settings = APISettings(
        rest={"metrics_enabled": False},
        admin_authentication={
            "mode": "jwt",
            "environment": "development",
            "jwt_header_name": "Authorization",
        },
    )
    service = OAuthService(MemoryHost(), ScriptedSessionFactory(""), MemoryDiscovery())
    headers = {
        "Authorization": "Bearer "
        + json.dumps(
            {
                "signature": "trusted",
                "claims": {"sub": "admin", "groups": ["umbod-admins"]},
            }
        )
    }
    with TestClient(create_app(settings, [], oauth_service=service)) as client:
        base = "/api/admin/connectors/mcp/oauth"
        assert client.get(base + "/status").status_code == 401
        assert client.post(base + "/fixture/begin", json={}).status_code == 401
        assert client.get(base + "/status", headers=headers).status_code == 200
        result = client.get(base + "/fixture", headers=headers)
        assert result.status_code == 200
        assert result.json()["requested_scopes"] == "read"
        assert not result.json()["has_authorization"]
        assert client.get(base + "/missing", headers=headers).status_code == 404
        assert (
            client.post(
                base + "/fixture/begin", json={"scopes": []}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.post(
                base + "/fixture/cancel", headers={**headers, "Cookie": "session=x"}
            ).status_code
            == 403
        )
        assert client.post(base + "/fixture/cancel", headers=headers).json() == {
            "status": "cancelled"
        }
        assert client.post(base + "/fixture/logout", headers=headers).json() == {
            "status": "signed_out"
        }
        assert (
            client.post(base + "/fixture/refresh", headers=headers).status_code == 422
        )
        schema = client.get("/api/admin/openapi.json", headers=headers).json()
        assert "/connectors/mcp/oauth/{connector_id}/begin" in schema["paths"]
    with TestClient(create_app(settings, [])) as client:
        result = client.get(base + "/fixture", headers=headers)
        assert result.status_code == 503
        assert result.json()["detail"]["code"] == "oauth_host_unavailable"
