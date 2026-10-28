import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.testclient import TestClient

from umbod.mcp.settings import MCPAppSettings
from tests.mcp_fixtures import create_test_mcp_http_app


@pytest.fixture(autouse=True)
def UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    availability_path = tmp_path / "connectors.json"
    availability_path.write_text(
        json.dumps({"connectors": [{"id": "slack"}, {"id": "test"}]}), encoding="utf-8"
    )
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))


@pytest.mark.parametrize("metrics_enabled", [False, True])
def test_health_route_reports_ready_without_authentication(
    metrics_enabled: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = MCPAppSettings(mcp={"metrics_enabled": metrics_enabled}, _env_file=None)
    original_settings = settings.model_dump()
    metrics_server = Mock(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(
        "umbod.mcp.public_app.McpMetricsHttpServer", Mock(return_value=metrics_server)
    )

    with TestClient(create_test_mcp_http_app(settings)) as client:
        response = client.get("/system/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    metrics_server.start.assert_not_awaited()
    metrics_server.stop.assert_not_awaited()
    assert settings.model_dump() == original_settings
