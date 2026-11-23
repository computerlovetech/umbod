from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.persistence_runtime import create_inmemory_runtime

from umbod.config import AppConfig
from umbod.core.persistence import PersistenceRuntime
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories


@dataclass(frozen=True)
class SetupApi:
    client: TestClient
    runtime: PersistenceRuntime


@pytest.fixture
def settings() -> AppConfig:
    return AppConfig(
        rest={"metrics_enabled": False},
        endpoints={"collector_base_url": "https://collector.example.test/otlp/"},
        otlp_receiver={"enabled": True, "bearer_token": "private-ingestion-secret"},
    )


@pytest.fixture
def api(
    settings: AppConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SetupApi]:
    deployment = tmp_path / "connectors.json"
    deployment.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, ())
    with TestClient(create_app_with_dependency_factories(factories)) as client:
        yield SetupApi(client=client, runtime=runtime)