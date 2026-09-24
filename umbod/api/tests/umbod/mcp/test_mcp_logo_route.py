import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from umbod.mcp.public_app import _LOGO_FILE, _LOGO_ROUTE
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


def test_logo_route_serves_bundled_png_without_authentication() -> None:
    settings = MCPAppSettings(_env_file=None)

    with TestClient(create_test_mcp_http_app(settings)) as client:
        response = client.get(_LOGO_ROUTE)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == _LOGO_FILE.read_bytes()


@pytest.mark.parametrize("path", ["/assets/", "/metrics"])
def test_private_routes_are_not_exposed_by_public_app(path: str) -> None:
    settings = MCPAppSettings(_env_file=None)

    with TestClient(create_test_mcp_http_app(settings)) as client:
        response = client.get(path)

    assert response.status_code == 404
