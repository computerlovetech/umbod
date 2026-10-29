import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from starlette.applications import Starlette

from tests.mcp_telemetry_fixtures import RecordingMetricsServer, RecordingMetricsServerFactory
from umbod.config import AppConfig
from umbod.core.persistence import Database, PersistenceRuntime
from umbod.core.persistence.runtime import PersistenceReadiness
from umbod.mcp.public_app import build_starlette_app, create_runtime_context, load_configured_public_app_config
from umbod.mcp.runtime_adapters import create_configured_downstream_client_factory, create_configured_openapi_runtime_adapters
from umbod.mcp.telemetry import McpMetricsServerFactory


class RecordingPersistenceRuntime:
    def __init__(self, delegate: PersistenceRuntime) -> None:
        self.delegate = delegate
        self.shutdowns = 0

    @property
    def database(self) -> Database:
        return self.delegate.database

    @property
    def readiness(self) -> PersistenceReadiness:
        return self.delegate.readiness

    async def shutdown(self) -> None:
        self.shutdowns += 1
        await self.delegate.shutdown()


class FailingMetricsServer(RecordingMetricsServer):
    def __init__(self, failure: type[BaseException]) -> None:
        super().__init__()
        self.failure = failure

    async def start(self) -> None:
        await super().start()
        raise self.failure()


class FailingMetricsServerFactory:
    def __init__(self, failure: type[BaseException]) -> None:
        self.server = FailingMetricsServer(failure)
        self.creates = 0

    def create(self) -> FailingMetricsServer:
        self.creates += 1
        return self.server


@pytest.fixture(autouse=True)
def deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "connectors.json"
    path.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(path))


async def create_application(enabled: bool, listeners: McpMetricsServerFactory) -> tuple[Starlette, RecordingPersistenceRuntime]:
    settings = AppConfig(mcp={"auth_mode": "none", "metrics_enabled": enabled, "downstream_discovery_enabled": False, "messaging_transport": "sql"})
    config = await load_configured_public_app_config(settings)
    persistence = RecordingPersistenceRuntime(config.persistence_runtime)
    config = replace(config, persistence_runtime=persistence, telemetry=replace(config.telemetry, metrics_server_factory=listeners))
    context = await create_runtime_context(config, downstream_client_factory=await create_configured_downstream_client_factory(config.settings, config.persistence_runtime.database), openapi_adapters=create_configured_openapi_runtime_adapters(config.settings))
    return await build_starlette_app(context), persistence


@pytest.mark.asyncio
async def test_enabled_listener_starts_and_stops_once_per_fresh_lifespan() -> None:
    listeners = RecordingMetricsServerFactory()
    app, persistence = await create_application(True, listeners)
    for _ in range(2):
        async with app.router.lifespan_context(app):
            assert listeners.servers[-1].starts == 1
            assert listeners.servers[-1].stops == 0
    assert len(listeners.servers) == 2
    assert listeners.servers[0] is not listeners.servers[1]
    assert [(server.starts, server.stops) for server in listeners.servers] == [(1, 1), (1, 1)]
    assert persistence.shutdowns == 2


@pytest.mark.asyncio
async def test_disabled_listener_is_never_created() -> None:
    listeners = RecordingMetricsServerFactory()
    app, persistence = await create_application(False, listeners)
    async with app.router.lifespan_context(app):
        assert listeners.servers == []
    assert listeners.servers == []
    assert persistence.shutdowns == 1


@pytest.mark.asyncio
async def test_lifespan_exception_stops_listener_and_shuts_down_persistence() -> None:
    listeners = RecordingMetricsServerFactory()
    app, persistence = await create_application(True, listeners)
    with pytest.RaisesGroup(pytest.RaisesExc(RuntimeError, match="request failed")):
        async with app.router.lifespan_context(app):
            raise RuntimeError("request failed")
    assert [(server.starts, server.stops) for server in listeners.servers] == [(1, 1)]
    assert persistence.shutdowns == 1


@pytest.mark.asyncio
async def test_lifespan_task_cancellation_stops_listener_and_shuts_down_persistence() -> None:
    listeners = RecordingMetricsServerFactory()
    app, persistence = await create_application(True, listeners)
    entered = asyncio.Event()

    async def run() -> None:
        async with app.router.lifespan_context(app):
            entered.set()
            await asyncio.wait_for(asyncio.Event().wait(), timeout=30)

    task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
    assert [(server.starts, server.stops) for server in listeners.servers] == [(1, 1)]
    assert persistence.shutdowns == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_failed_listener_start_is_not_stopped_and_persistence_shuts_down(failure: type[BaseException]) -> None:
    listeners = FailingMetricsServerFactory(failure)
    app, persistence = await create_application(True, listeners)
    expected_failure = pytest.RaisesGroup(RuntimeError) if failure is RuntimeError else pytest.raises(failure)
    with expected_failure:
        async with app.router.lifespan_context(app):
            pytest.fail("Failed metrics startup must not enter application lifespan")
    assert listeners.creates == 1
    assert listeners.server.starts == 1
    assert listeners.server.stops == 0
    assert persistence.shutdowns == 1
