from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from tests.umbod.rest.user_catalogue.query_budget_support import CountingRuntime, QueryCounts
from tests.umbod.rest.user_catalogue.test_catalogue_query_budget import seed_shared_tools
from umbod.config import AppConfig
from umbod.core.activation import ActivationStatus, CapabilityActivationState, CapabilityRef
from umbod.core.activation.stores.schema import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.downstream_mcp.stores import CONNECTOR_DEFINITION_TABLE, TOOL_CATALOG_TABLE
from umbod.core.connectors.openapi.stores.schema import CONNECTOR_TABLE
from umbod.core.permissions import AssignablePermissionCatalog
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app
from umbod.rest.mcp_permissions.schemas import AssignablePermissionTargetsResponse


AdminPermissionHttp = tuple[TestClient, FastAPI, ConnectorApiDependencyFactories, QueryCounts]


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


def read_assignable_targets(
    client: TestClient, counts: QueryCounts,
) -> AssignablePermissionTargetsResponse:
    counts.reset()
    response = client.get("/api/admin/mcp-permissions/assignable-targets")
    assert response.status_code == 200, response.text
    assert not counts.writes
    assert counts.schema_calls == 0
    return AssignablePermissionTargetsResponse.model_validate(response.json())


def assert_shared_targets(
    targets: AssignablePermissionTargetsResponse, keys: set[str],
) -> None:
    assert [connector.model_dump() for connector in targets.connectors] == (
        [{"connector_id": "shared", "display_name": "Shared"}] if keys else []
    )
    assert [capability.model_dump() for capability in targets.capabilities] == [
        {
            "connector_id": "shared", "capability_kind": "tool",
            "capability_key": key, "display_name": key,
        }
        for key in sorted(keys)
    ]


@pytest.mark.parametrize("tool_count", [1, 40, 100])
def test_assignable_targets_only_activation_reads_grow_with_shared_tool_count(
    admin_permission_http: AdminPermissionHttp, tool_count: int,
) -> None:
    client, _, factories, counts = admin_permission_http
    client.portal.call(seed_shared_tools, factories, tool_count)

    targets = read_assignable_targets(client, counts)

    assert_shared_targets(targets, {f"read_{index}" for index in range(tool_count)})
    assert counts.reads == Counter({
        CONNECTOR_TABLE.name: 1,
        CONNECTOR_DEFINITION_TABLE.name: 2,
        TOOL_CATALOG_TABLE.name: 1,
        PUBLICATION_STATE_TABLE.name: 1,
        CAPABILITY_ACTIVATION_STATE_TABLE.name: tool_count,
    })
    assert counts.sessions == tool_count + 5


async def set_shared_publication(
    factories: ConnectorApiDependencyFactories, published: bool,
) -> None:
    store = await factories.connector_publishing_store.create()
    if published:
        await store.publish_connector("shared")
    else:
        await store.unpublish_connector("shared")


async def disable_shared_tool(factories: ConnectorApiDependencyFactories) -> None:
    store = await factories.capability_activation_store.create()
    await store.set_statuses((CapabilityActivationState(
        ref=CapabilityRef(
            connector_kind="downstream_mcp", connector_id="shared",
            capability_kind="tool", capability_key="read_0",
        ),
        activation_status=ActivationStatus.DISABLED,
    ),))


def test_assignable_targets_observe_publication_withdrawal_and_restoration_next_request(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    client, _, factories, counts = admin_permission_http
    client.portal.call(seed_shared_tools, factories, 2)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0", "read_1"})

    client.portal.call(set_shared_publication, factories, False)
    assert_shared_targets(read_assignable_targets(client, counts), set())

    client.portal.call(set_shared_publication, factories, True)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0", "read_1"})


def test_assignable_targets_observe_disabled_activation_next_request(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    client, _, factories, counts = admin_permission_http
    client.portal.call(seed_shared_tools, factories, 2)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0", "read_1"})

    client.portal.call(disable_shared_tool, factories)

    assert_shared_targets(read_assignable_targets(client, counts), {"read_1"})


def test_assignable_targets_observe_replaced_catalogue_next_request(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    client, _, factories, counts = admin_permission_http
    client.portal.call(seed_shared_tools, factories, 2)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0", "read_1"})

    client.portal.call(seed_shared_tools, factories, 1)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0"})

    client.portal.call(seed_shared_tools, factories, 3)
    assert_shared_targets(
        read_assignable_targets(client, counts), {"read_0", "read_1", "read_2"},
    )


def test_permission_mutation_does_not_use_assignable_targets_cached_provider(
    admin_permission_http: AdminPermissionHttp,
) -> None:
    from umbod.rest.mcp_permissions.dependencies import get_assignable_permission_catalog

    client, app, factories, counts = admin_permission_http
    client.portal.call(seed_shared_tools, factories, 2)
    assert_shared_targets(read_assignable_targets(client, counts), {"read_0", "read_1"})

    def reject_cached_catalog() -> AssignablePermissionCatalog:
        raise AssertionError("Permission mutations must not use the assignable GET catalog")

    app.dependency_overrides[get_assignable_permission_catalog] = reject_cached_catalog
    response = client.put("/api/admin/mcp-permissions/groups/readers/permissions", json={
        "connectors": [],
        "capabilities": [{
            "connector_id": "shared", "capability_kind": "tool",
            "capability_key": "read_0", "permission_status": "disabled",
        }],
    })
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "applied", "group_id": "readers"}

    group = client.get("/api/admin/mcp-permissions/groups/readers")
    assert group.status_code == 200, group.text
    assert group.json() == {
        "group_id": "readers", "connector_ids": [],
        "capabilities": [{
            "connector_id": "shared", "capability_kind": "tool", "capability_key": "read_1",
        }],
    }
