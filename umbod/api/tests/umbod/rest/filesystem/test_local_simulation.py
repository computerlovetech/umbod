from umbod.core.filesystem.namespace import ROOT_ID
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from umbod.config import AppConfig
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import AppPersistenceRuntime
from tests.persistence_runtime import create_inmemory_runtime
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories

BASE = "/api/me/filesystem"
POLICY = "/api/admin/filesystem/root-access"


@pytest.fixture
def local_filesystem_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    return AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "inmemory"},
        runtime={"profile": "local", "auth": "dev"},
        admin_authentication={
            "mode": "simulation", "environment": "development", "simulated_admin": True,
            "simulated_user_id": "test-user", "membership_claim": "groups", "required_membership": "admin",
        },
        mcp={"permission_group_claim": "groups"},
    )


@pytest_asyncio.fixture
async def local_filesystem_runtime() -> AsyncIterator[PersistenceRuntime]:
    runtime = create_inmemory_runtime()
    try:
        yield runtime
    finally:
        await runtime.shutdown()


@asynccontextmanager
async def _local_filesystem_client(settings: AppConfig, runtime: PersistenceRuntime) -> AsyncIterator[AsyncClient]:
    application_runtime = AppPersistenceRuntime(database=runtime.database, readiness=runtime.readiness)
    factories = ConnectorApiDependencyFactories.from_settings(settings, application_runtime, [])
    app = create_app_with_dependency_factories(factories)
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_local_personal_namespace_is_private_and_idempotent(
    local_filesystem_settings: AppConfig, local_filesystem_runtime: PersistenceRuntime,
) -> None:
    async with _local_filesystem_client(local_filesystem_settings, local_filesystem_runtime) as client:
        assert (await client.get(BASE + f"/browse?node_id={ROOT_ID}")).status_code == 403
        first = await client.post(BASE + "/home")
        repeated = await client.post(BASE + "/home")
        assert first.status_code == repeated.status_code == 200
        assert first.json() == repeated.json()
        home = first.json()
        namespace = (await client.get(BASE + "/namespaces")).json()["namespaces"][0]
        assert home["visible_to"] == {
            "type": "namespace", "namespace_id": namespace["id"], "kind": "personal", "name": namespace["name"],
        }
        assert set(home["permissions"]) == {"can_discover", "can_read", "can_write", "can_delete", "can_share"}
        created = await client.post(BASE + f"/nodes/{home['id']}/directories", json={
            "name": "private", "metadata": {"content_type": {}, "attributes": {}},
        })
        assert created.status_code == 201
        child = created.json()
        assert (await client.get(BASE + "/browse")).json()["entries"] == [child]
        assert (await client.get(POLICY)).status_code == 404
    other_settings = AppConfig.model_validate({
        **local_filesystem_settings.model_dump(),
        "admin_authentication": {
            **local_filesystem_settings.admin_authentication.model_dump(), "simulated_user_id": "other-user",
        },
    })
    async with _local_filesystem_client(other_settings, local_filesystem_runtime) as other:
        assert (await other.get(BASE + f"/nodes/{child['id']}")).status_code == 403
        other_home = await other.post(BASE + "/home")
        assert other_home.status_code == 200
        assert other_home.json()["id"] != home["id"]
    async with _local_filesystem_client(local_filesystem_settings, local_filesystem_runtime) as owner:
        assert (await owner.get(BASE + f"/nodes/{child['id']}")).json() == child


@pytest.mark.asyncio
async def test_local_namespace_ignores_client_selected_identity(
    local_filesystem_settings: AppConfig, local_filesystem_runtime: PersistenceRuntime,
) -> None:
    async with _local_filesystem_client(local_filesystem_settings, local_filesystem_runtime) as client:
        home = (await client.post(BASE + "/home")).json()
        response = await client.get(BASE + f"/nodes/{home['id']}", headers={
            "Authorization": 'Bearer {"iss":"attacker","sub":"test-user","groups":["admin"]}',
            "X-Umbod-Issuer": "attacker",
        })
        assert response.status_code == 200
        assert response.json() == home
