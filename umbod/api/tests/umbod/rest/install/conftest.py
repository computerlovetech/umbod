from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.config import AppConfig
from umbod.rest.main import create_app


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "inmemory"},
        admin_authentication={"mode": "jwt", "environment": "development"},
        endpoints={"mcp_base_url": "https://configured.test/team/"},
    )


@pytest.fixture
def client(settings: AppConfig) -> Iterator[TestClient]:
    with TestClient(create_app(settings, [])) as client:
        yield client


