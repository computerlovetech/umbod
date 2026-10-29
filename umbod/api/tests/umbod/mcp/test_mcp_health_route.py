import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from tests.mcp_telemetry_fixtures import RecordingMetricsServerFactory
from umbod.config import AppConfig
from umbod.mcp.public_app import build_starlette_app, create_runtime_context, load_configured_public_app_config
from umbod.mcp.runtime_adapters import create_configured_downstream_client_factory, create_configured_openapi_runtime_adapters
from umbod.mcp.settings import MCPAppSettings


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
    metrics_enabled: bool
) -> None:
    settings = MCPAppSettings(mcp={"metrics_enabled": metrics_enabled, "messaging_transport": "sql"}, _env_file=None)
    original_settings = settings.model_dump()
    listeners = RecordingMetricsServerFactory()

    async def create_app() -> Starlette:
        config = await load_configured_public_app_config(AppConfig.model_validate(settings.model_dump()))
        config = replace(config, telemetry=replace(config.telemetry, metrics_server_factory=listeners))
        context = await create_runtime_context(config, downstream_client_factory=await create_configured_downstream_client_factory(config.settings, config.persistence_runtime.database), openapi_adapters=create_configured_openapi_runtime_adapters(config.settings))
        return await build_starlette_app(context)

    with TestClient(asyncio.run(create_app())) as client:
        response = client.get("/system/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert [(server.starts, server.stops) for server in listeners.servers] == ([(1, 1)] if metrics_enabled else [])
    assert settings.model_dump() == original_settings
