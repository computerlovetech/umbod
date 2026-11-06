from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbod.config import AppConfig
from umbod.core.persistence import Database, PersistenceReadiness, PersistenceRuntime
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories
from tests.persistence_runtime import create_inmemory_runtime


class ObservedRuntime:
    def __init__(self, runtime: PersistenceRuntime) -> None:
        self._runtime = runtime
        self.database: Database = runtime.database
        self.readiness: PersistenceReadiness = runtime.readiness
        self.shutdown_calls: int = 0

    async def shutdown(self) -> None:
        self.shutdown_calls += 1
        await self._runtime.shutdown()


@pytest.fixture
def supplied_factories() -> tuple[ConnectorApiDependencyFactories, ObservedRuntime]:
    runtime = ObservedRuntime(create_inmemory_runtime())
    settings = AppConfig(rest={"metrics_enabled": False})
    return ConnectorApiDependencyFactories.from_settings(settings, runtime, []), runtime


@pytest.fixture
def connector_deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "deployment.json"
    path.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(path))
    return path


@pytest.mark.usefixtures("connector_deployment")
def test_supplied_factories_reuse_the_runtime_and_own_its_shutdown(
    supplied_factories: tuple[ConnectorApiDependencyFactories, ObservedRuntime], monkeypatch: pytest.MonkeyPatch,
) -> None:
    factories, runtime = supplied_factories

    def unexpected_selection(provider: ConfiguredPersistenceRuntimeProvider) -> PersistenceRuntime:
        raise AssertionError("Supplied factories must not select another runtime")

    monkeypatch.setattr(ConfiguredPersistenceRuntimeProvider, "create", unexpected_selection)
    app = create_app_with_dependency_factories(factories)
    with TestClient(app) as client:
        assert client.get("/api/system/health").status_code == 200
        assert runtime.shutdown_calls == 0
    assert runtime.shutdown_calls == 1


@pytest.mark.usefixtures("connector_deployment")
def test_supplied_runtime_is_closed_when_readiness_fails(
    supplied_factories: tuple[ConnectorApiDependencyFactories, ObservedRuntime], monkeypatch: pytest.MonkeyPatch,
) -> None:
    factories, runtime = supplied_factories

    async def failed_readiness() -> None:
        raise RuntimeError("readiness failed")

    monkeypatch.setattr(runtime.readiness, "ensure_ready", failed_readiness)
    with pytest.raises(RuntimeError, match="readiness failed"), TestClient(create_app_with_dependency_factories(factories)):
        pytest.fail("Failed readiness must not enter the application lifespan")
    assert runtime.shutdown_calls == 1


@pytest.mark.parametrize("argument", ["settings", "connector_registrations"])
def test_supplied_factories_reject_competing_configuration(
    supplied_factories: tuple[ConnectorApiDependencyFactories, ObservedRuntime], argument: str,
) -> None:
    factories, _ = supplied_factories
    value = factories.settings if argument == "settings" else []
    with pytest.raises(TypeError, match="from its factories"):
        create_app_with_dependency_factories(factories, **{argument: value})
