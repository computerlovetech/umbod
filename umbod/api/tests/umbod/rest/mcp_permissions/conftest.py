from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.routing import Mount
from fastapi.testclient import TestClient

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from tests.umbod.rest.mcp_permissions.assignable_support import AdminPermissionHttp
from tests.umbod.rest.user_catalogue.query_budget_support import CountingRuntime, QueryCounts
from umbod.config import AppConfig
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app


@pytest.fixture(params=["inmemory", "sqlite"])
def admin_permission_http(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[AdminPermissionHttp]:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "inmemory"},
        admin_authentication={
            "mode": "simulation", "environment": "development", "simulated_admin": True,
        },
        personal_connections={"enabled": False},
    )
    root = create_app(settings, [])
    app = next(
        route.app for route in root.routes
        if isinstance(route, Mount) and route.path == "/api/admin"
    )
    with TestClient(root) as client:
        runtime = (
            client.portal.call(prepared_inmemory_runtime)
            if request.param == "inmemory"
            else client.portal.call(prepared_sqlite_runtime, tmp_path / "permissions.sqlite")
        )
        counts = QueryCounts()
        wrapped_runtime = CountingRuntime(runtime, counts)
        factories = ConnectorApiDependencyFactories.from_settings(settings, wrapped_runtime, [])

        def permission_factories() -> ConnectorApiDependencyFactories:
            return factories

        app.dependency_overrides[get_connector_api_dependency_factories] = permission_factories
        try:
            yield client, app, factories, counts
        finally:
            app.dependency_overrides.clear()
            client.portal.call(wrapped_runtime.shutdown)

