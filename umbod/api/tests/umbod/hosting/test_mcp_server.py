import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass, replace
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import pytest_asyncio

from umbod.config import AppConfig, McpAdministratorConfig
from umbod.core.persistence import Database, PersistenceReadiness, PersistenceRuntime
from umbod.hosting import mcp_server
from umbod.hosting.listeners import HttpListener
from umbod.mcp.context import PublicAppConfig
from umbod.mcp.runtime_options import StoreBackedConnectorRuntimeStateSourceStrategy


@dataclass
class TrackedPersistence:
    runtime: PersistenceRuntime
    stopping: asyncio.Event
    shutdown_count: int = 0

    @property
    def database(self) -> Database:
        return self.runtime.database

    @property
    def readiness(self) -> PersistenceReadiness:
        return self.runtime.readiness

    async def shutdown(self) -> None:
        assert self.stopping.is_set()
        self.shutdown_count += 1
        await self.runtime.shutdown()


@pytest_asyncio.fixture
async def configured_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[PublicAppConfig, TrackedPersistence]]:
    declaration = tmp_path / "connectors.json"
    declaration.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(declaration))
    settings = AppConfig.model_validate({
        "mcp": {"auth_mode": "none", "metrics_enabled": False, "messaging_transport": "sql"},
        "connector_store": {"type": "inmemory"},
        "telemetry_analytics": {"enabled": False},
    })
    config = await mcp_server.load_configured_public_app_config(settings)
    persistence = TrackedPersistence(config.persistence_runtime, asyncio.Event())
    config = replace(
        config, persistence_runtime=persistence,
        configured_source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(),
        api_base_url=None,
    )
    monkeypatch.setattr(mcp_server, "load_configured_public_app_config", AsyncMock(return_value=config))
    try:
        yield config, persistence
    finally:
        if persistence.shutdown_count == 0:
            persistence.stopping.set()
            await persistence.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,enabled,count", [
    ("shared", True, 1), ("separate", True, 2),
    ("shared", False, 1), ("separate", False, 1),
])
async def test_host_starts_only_configured_listeners_and_closes_shared_persistence_once(
    configured_runtime: tuple[PublicAppConfig, TrackedPersistence],
    monkeypatch: pytest.MonkeyPatch, mode: str, enabled: bool, count: int,
) -> None:
    config, persistence = configured_runtime
    settings = AppConfig.model_validate({
        **config.settings.model_dump(),
        "mcp_administrator": {"hosting": mode},
        "feature_toggles": {"mcp_administrator_enabled": enabled},
    })
    config = replace(config, settings=settings)
    monkeypatch.setattr(mcp_server, "load_configured_public_app_config", AsyncMock(return_value=config))
    observed: list[HttpListener] = []

    async def serve(listeners: tuple[HttpListener, ...], stopping: asyncio.Event) -> None:
        observed.extend(listeners)
        async with AsyncExitStack() as stack:
            for listener in listeners:
                await stack.enter_async_context(listener.app.router.lifespan_context(listener.app))
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(listener.app), base_url="http://test",
                ) as client:
                    assert (await client.get("/system/health")).status_code == 200
            assert persistence.shutdown_count == 0
        assert persistence.shutdown_count == 0
        stopping.set()

    monkeypatch.setattr(mcp_server, "serve_listeners", serve)
    await mcp_server.serve_mcp(settings, "127.0.0.2", 9200, persistence.stopping)
    assert len(observed) == count
    assert observed[0].host == "127.0.0.2"
    assert observed[0].port == 9200
    if count == 2:
        assert observed[1].host == settings.mcp_administrator.host
        assert observed[1].port == settings.mcp_administrator.port
    assert persistence.shutdown_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_admin_application_construction_failure_closes_host_owned_persistence(
    configured_runtime: tuple[PublicAppConfig, TrackedPersistence],
    monkeypatch: pytest.MonkeyPatch, failure: type[BaseException],
) -> None:
    config, persistence = configured_runtime
    settings = config.settings.model_copy(update={
        "mcp_administrator": McpAdministratorConfig(hosting="separate"),
    })
    config = replace(config, settings=settings)
    monkeypatch.setattr(mcp_server, "load_configured_public_app_config", AsyncMock(return_value=config))
    monkeypatch.setattr(mcp_server, "build_administrator_app", AsyncMock(side_effect=failure()))
    with pytest.raises(failure):
        await mcp_server.serve_mcp(settings, "127.0.0.1", 9200, persistence.stopping)
    assert persistence.shutdown_count == 1


@pytest.mark.asyncio
async def test_occupied_admin_port_cleans_up_before_any_application_lifespan(
    configured_runtime: tuple[PublicAppConfig, TrackedPersistence],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, persistence = configured_runtime
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            public_port = available.getsockname()[1]
        settings = config.settings.model_copy(update={
            "mcp_administrator": McpAdministratorConfig(hosting="separate", port=port),
        })
        config = replace(config, settings=settings)
        monkeypatch.setattr(mcp_server, "load_configured_public_app_config", AsyncMock(return_value=config))
        with pytest.raises(RuntimeError, match="Unable to bind HTTP listeners"):
            await mcp_server.serve_mcp(settings, "127.0.0.1", public_port, persistence.stopping)
    assert persistence.shutdown_count == 1


@pytest.mark.parametrize("port", [0, 65536, 8000, 8001, 8012])
def test_effective_public_port_rejects_invalid_and_reserved_ports(port: int) -> None:
    with pytest.raises(ValueError):
        mcp_server.validate_listener_ports(AppConfig(), port)


def test_effective_public_port_cannot_collide_with_separate_admin_listener() -> None:
    settings = AppConfig(mcp_administrator=McpAdministratorConfig(hosting="separate"))
    with pytest.raises(ValueError, match="Administrator MCP listener port"):
        mcp_server.validate_listener_ports(settings, 8013)


def test_reload_uses_one_supervisor_for_all_mcp_listeners(monkeypatch: pytest.MonkeyPatch) -> None:
    reload_supervisor = Mock()
    monkeypatch.setattr(mcp_server, "ChangeReload", reload_supervisor)
    settings = AppConfig(mcp_administrator=McpAdministratorConfig(hosting="separate"))
    mcp_server.run_mcp_server(settings, "127.0.0.2", 9200, reload=True)
    arguments = reload_supervisor.call_args.kwargs
    assert arguments["sockets"] == []
    assert arguments["target"].keywords == {"host": "127.0.0.2", "port": 9200}
    reload_supervisor.return_value.run.assert_called_once_with()
