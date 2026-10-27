import importlib
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from typer.testing import CliRunner

import umbod.hosting as hosting
from umbod.config import AppConfig
from umbod.hosting import rest_service


def test_rest_service_loads_environment_and_configures_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppConfig()
    load = Mock(return_value=settings)
    configure = Mock()
    build = Mock(return_value=FastAPI())
    monkeypatch.setattr(rest_service, "load_server_app_config", load)
    monkeypatch.setattr(rest_service, "configure_logging", configure)
    monkeypatch.setattr(rest_service, "create_rest_app", build)
    assert rest_service.create_app() is build.return_value
    load.assert_called_once_with(".env")
    configure.assert_called_once_with(settings.runtime.app_name, settings.runtime.log_level)
    build.assert_called_once_with(settings, connector_registrations=None, admin_verifier=None, oauth_service=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_mcp_service_defers_composition_and_owns_forwarding_lifespan(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(application: Starlette) -> AsyncIterator[None]:
        events.append("start")
        try:
            yield
        finally:
            events.append("stop")

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    application = Starlette(routes=[Route("/system/health", health)], lifespan=lifespan)
    settings = AppConfig()
    load = Mock(return_value=settings)
    configure = Mock()
    build = AsyncMock(return_value=application, side_effect=RuntimeError("construction failed") if failure else None)
    monkeypatch.setattr("umbod.config.load_server_app_config", load)
    monkeypatch.setattr("umbod.logging.configure_logging", configure)
    monkeypatch.setattr(hosting, "create_mcp_app", build)
    for name in ("umbod.hosting.mcp_service", "umbod.mcp.main"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    try:
        config = uvicorn.Config("umbod.hosting.mcp_service:app", log_config=None)
        config.load()
        service = importlib.import_module("umbod.hosting.mcp_service")
        legacy = importlib.import_module("umbod.mcp.main")
        assert legacy.app is service.app
        build.assert_not_called()
        load.assert_not_called()
        configure.assert_not_called()
        original_routes = list(service.app.routes)
        if failure:
            with pytest.raises(RuntimeError, match="construction failed"):
                async with service.app.router.lifespan_context(service.app):
                    pytest.fail("Startup should fail")
            assert events == []
        else:
            async with service.app.router.lifespan_context(service.app):
                assert events == ["start"]
                async with httpx.AsyncClient(transport=httpx.ASGITransport(service.app), base_url="http://test") as client:
                    assert (await client.get("/system/health")).json() == {"status": "ok"}
            assert events == ["start", "stop"]
        assert service.app.routes == original_routes
        load.assert_called_once_with(".env")
        configure.assert_called_once_with(settings.runtime.app_name, settings.runtime.log_level)
        build.assert_awaited_once_with(settings, auth_provider=None, group_permission_runtime_state=None, invocation_log_sink=None)
    finally:
        sys.modules.pop("umbod.hosting.mcp_service", None)
        sys.modules.pop("umbod.mcp.main", None)


def test_fresh_process_uvicorn_serves_mcp_public_health(tmp_path: Path) -> None:
    program = '''
import asyncio
import socket
import httpx
import uvicorn
import umbod.config

async def verify() -> None:
    settings = umbod.config.AppConfig.model_validate({
        "mcp": {"auth_mode": "none", "metrics_enabled": False},
        "connector_store": {"type": "sqlite", "sqlite_path": "backend.sqlite3"},
    })
    umbod.config.load_server_app_config = lambda path: settings
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config("umbod.hosting.mcp_service:app", log_level="error"))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(15):
                while not server.started:
                    if task.done():
                        await task
                        raise AssertionError("Server stopped before startup")
                    await asyncio.sleep(0.01)
            async with httpx.AsyncClient(base_url=origin) as client:
                response = await client.get("/system/health")
                assert response.status_code == 200
                assert response.json() == {"status": "ok"}
        finally:
            server.should_exit = True
            await task

asyncio.run(verify())
'''
    declaration = tmp_path / "connectors.json"
    declaration.write_text('{"connectors": []}')
    import os

    environment = dict(os.environ, UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH=str(declaration))
    result = subprocess.run([sys.executable, "-c", program], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_rest_cli_uses_hosting_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    from umbod.cli import api

    run = Mock()
    monkeypatch.setattr(api, "load_server_app_config", Mock(return_value=AppConfig()))
    monkeypatch.setattr(api, "configure_logging", Mock())
    monkeypatch.setattr(api.uvicorn, "run", run)
    result = CliRunner().invoke(api.app, [])
    assert result.exit_code == 0, result.output
    assert run.call_args.args == ("umbod.hosting.rest_service:create_app",)
    assert run.call_args.kwargs["factory"] is True


def test_legacy_rest_factory_accepts_positional_and_keyword_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from umbod.rest.main import create_app

    declaration = tmp_path / "connectors.json"
    declaration.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(declaration))
    settings = AppConfig()
    assert isinstance(create_app(settings, []), FastAPI)
    assert isinstance(create_app(settings=settings, connector_registrations=[]), FastAPI)
