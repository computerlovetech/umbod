import importlib
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from umbod.hosting import rest_service
from umbod.mcp import public_app
from umbod.rest import main as rest_main


@pytest.fixture(autouse=True, params=[None, "UMBOD_REST_PORT", "UMBOD_MCP_PORT", "UMBOD_OTLP_ENABLED"])
def missing_root_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UMBOD_ROOT_SECRET", raising=False)
    if request.param is not None:
        monkeypatch.setenv(request.param, "invalid")


def test_rest_service_rejects_missing_root_before_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = Mock()
    configure = Mock()
    monkeypatch.setattr(rest_service, "create_rest_app", build)
    monkeypatch.setattr(rest_service, "configure_logging", configure)
    with pytest.raises(ValueError, match="UMBOD_ROOT_SECRET"):
        rest_service.create_app()
    build.assert_not_called()
    configure.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_import_is_safe_and_startup_rejects_missing_root_before_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = importlib.import_module("umbod.hosting.mcp_service")
    build = AsyncMock()
    configure = Mock()
    monkeypatch.setattr(service, "create_mcp_app", build)
    monkeypatch.setattr(service, "configure_logging", configure)
    original_routes = list(service.app.routes)
    with pytest.raises(ValueError, match="UMBOD_ROOT_SECRET"):
        async with service.app.router.lifespan_context(service.app):
            pytest.fail("Startup must reject missing root")
    build.assert_not_awaited()
    configure.assert_not_called()
    assert service.app.routes == original_routes


def test_legacy_rest_environment_factory_rejects_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistence = Mock()
    monkeypatch.setattr(rest_main, "ConfiguredPersistenceRuntimeProvider", persistence)
    with pytest.raises(ValueError, match="UMBOD_ROOT_SECRET"):
        rest_main.create_app()
    persistence.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_mcp_environment_factory_rejects_before_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = AsyncMock()
    monkeypatch.setattr("umbod.hosting.create_mcp_app", build)
    with pytest.raises(ValueError, match="UMBOD_ROOT_SECRET"):
        await public_app.create_production_app()
    build.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_mcp_environment_configuration_rejects_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load = AsyncMock()
    monkeypatch.setattr(public_app, "load_configured_public_app_config", load)
    with pytest.raises(ValueError, match="UMBOD_ROOT_SECRET"):
        await public_app.load_production_public_app_config()
    load.assert_not_awaited()
