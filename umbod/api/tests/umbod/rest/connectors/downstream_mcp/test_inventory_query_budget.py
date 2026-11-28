from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from starlette.routing import Mount

from tests.persistence_runtime import create_inmemory_runtime, prepared_inmemory_runtime
from tests.umbod.rest.user_catalogue.query_budget_support import CountingRuntime, QueryCounts
from umbod.config import AppConfig
from umbod.core.connectors.downstream_mcp.adapters.settings import (
    downstream_mcp_infrastructure_settings_from_app_config,
)
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorHealthy,
    ConnectorUnhealthy,
    DiscoveredServerIcon,
    NoAuthConnectorDefinition,
    OAuthConnectorDefinition,
    StaticBearerConnectorDefinition,
    ToolCatalogSnapshot,
)
from umbod.core.connectors.downstream_mcp.stores import (
    CONNECTOR_DEFINITION_TABLE,
    CONNECTOR_HEALTH_TABLE,
    TOOL_CATALOG_TABLE,
    DownstreamMcpStores,
    ReplaceToolCatalog,
    SaveConnectorDefinition,
    SaveConnectorHealth,
    create_downstream_mcp_stores,
)
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.publishing.factories import create_connector_publishing_store
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.rest.connectors.dependencies import get_connector_publishing_store
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories

InventoryHttp = tuple[TestClient, DownstreamMcpStores, QueryCounts]


@pytest.fixture
def inventory_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[InventoryHttp]:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        connector_store={"type": "inmemory"},
        admin_authentication={"mode": "simulation", "simulated_admin": True},
        rest={"metrics_enabled": False},
    )
    counts = QueryCounts()
    runtime = CountingRuntime(create_inmemory_runtime(), counts)
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, [])
    with TestClient(create_app_with_dependency_factories(factories)) as client:
        secret = downstream_mcp_infrastructure_settings_from_app_config(settings).credential_secret
        stores = client.portal.call(create_downstream_mcp_stores, secret, runtime.database)
        yield client, stores, counts


def _get_inventory(client: TestClient, counts: QueryCounts) -> Response:
    counts.reset()
    response = client.get("/api/admin/connectors/mcp")
    assert response.status_code == 200, response.text
    return response


def _assert_read_budget(counts: QueryCounts, reads: dict[str, int], sessions: int) -> None:
    assert counts.reads == reads
    assert counts.sessions == sessions
    assert not counts.writes
    assert counts.schema_calls == 0


def _assert_nonempty_read_budget(counts: QueryCounts, state_batches: int) -> None:
    _assert_read_budget(counts, {
        CONNECTOR_DEFINITION_TABLE.name: 1,
        TOOL_CATALOG_TABLE.name: state_batches,
        CONNECTOR_HEALTH_TABLE.name: state_batches,
        PUBLICATION_STATE_TABLE.name: state_batches,
    }, sessions=2)


async def _seed_connector_state(stores: DownstreamMcpStores, connector_id: str) -> None:
    checked_at = datetime(2026, 1, 1, tzinfo=UTC)
    await stores.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(
        connector_id=connector_id, discovered_at=checked_at, tools=(),
        server_icons=(DiscoveredServerIcon(src="https://example.test/icon.png"),),
    )))
    await stores.health.save(SaveConnectorHealth(health=ConnectorHealthy(
        connector_id=connector_id, checked_at=checked_at,
    )))
    await stores.publishing.publish_connector(connector_id)


@pytest.mark.parametrize(("connector_count", "state_batches"), ((1, 1), (50, 1), (201, 2)))
def test_inventory_read_budget_grows_by_batch_not_by_connector(
    inventory_http: InventoryHttp, connector_count: int, state_batches: int,
) -> None:
    client, stores, counts = inventory_http
    connector_ids = [f"connector-{index:03d}" for index in range(connector_count)]
    for connector_id in reversed(connector_ids):
        client.portal.call(stores.definitions.save, SaveConnectorDefinition(
            definition=NoAuthConnectorDefinition(
                connector_id=connector_id, display_name=connector_id,
                endpoint_url="https://example.test/mcp",
            ),
        ))

    client.portal.call(_seed_connector_state, stores, connector_ids[-1])

    response = _get_inventory(client, counts)

    connectors = response.json()["connectors"]
    assert [item["connector_id"] for item in connectors] == connector_ids
    assert connectors[-1]["icon_url"] == "https://example.test/icon.png"
    assert connectors[-1]["health"]["status"] == "healthy"
    assert connectors[-1]["publication_status"] == "published"
    _assert_nonempty_read_budget(counts, state_batches)


def test_empty_inventory_reads_only_definitions(inventory_http: InventoryHttp) -> None:
    client, _, counts = inventory_http

    response = _get_inventory(client, counts)

    assert response.json() == {"connectors": []}
    _assert_read_budget(counts, {CONNECTOR_DEFINITION_TABLE.name: 1}, sessions=1)


async def _seed_mixed_inventory(stores: DownstreamMcpStores) -> None:
    endpoint_url = "https://example.test/mcp"
    checked_at = datetime(2026, 1, 1, tzinfo=UTC)
    for definition in (
        NoAuthConnectorDefinition(
            connector_id="gamma", display_name="First by Name", endpoint_url=endpoint_url,
        ),
        OAuthConnectorDefinition(
            connector_id="beta", display_name="Personal", endpoint_url=endpoint_url,
            authorization_mode="personal",
        ),
        StaticBearerConnectorDefinition(
            connector_id="alpha", display_name="Shared Bearer", endpoint_url=endpoint_url,
        ),
    ):
        await stores.definitions.save(SaveConnectorDefinition(definition=definition))
    await stores.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(
        connector_id="alpha", discovered_at=checked_at, tools=(), server_icons=(
            DiscoveredServerIcon(src="https://example.test/z-icon.png"),
            DiscoveredServerIcon(src="https://example.test/a-icon.png"),
        ),
    )))
    await stores.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(
        connector_id="gamma", discovered_at=checked_at, tools=(), server_icons=(),
    )))
    await stores.health.save(SaveConnectorHealth(health=ConnectorUnhealthy(
        connector_id="alpha", checked_at=checked_at, reason="timeout",
    )))
    await stores.health.save(SaveConnectorHealth(health=ConnectorHealthy(
        connector_id="gamma", checked_at=checked_at,
    )))
    await stores.publishing.publish_connector("alpha")
    await stores.publishing.publish_connector("gamma")
    await stores.publishing.unpublish_connector("gamma")


def test_inventory_preserves_order_and_projects_mixed_connector_state(
    inventory_http: InventoryHttp,
) -> None:
    client, stores, counts = inventory_http
    client.portal.call(_seed_mixed_inventory, stores)

    response = _get_inventory(client, counts)

    assert response.json() == {"connectors": [
        {
            "connector_id": "alpha",
            "display_name": "Shared Bearer",
            "icon_url": "https://example.test/z-icon.png",
            "auth_mode": "static_bearer",
            "authorization_mode": "shared",
            "publication_status": "published",
            "health": {"status": "unhealthy", "checked_at": "2026-01-01T00:00:00Z", "reason": "timeout"},
        },
        {
            "connector_id": "beta",
            "display_name": "Personal",
            "icon_url": "",
            "auth_mode": "oauth",
            "authorization_mode": "personal",
            "publication_status": "unpublished",
            "health": {"status": "unknown", "checked_at": None, "reason": None},
        },
        {
            "connector_id": "gamma",
            "display_name": "First by Name",
            "icon_url": "",
            "auth_mode": "none",
            "authorization_mode": "shared",
            "publication_status": "unpublished",
            "health": {"status": "healthy", "checked_at": "2026-01-01T00:00:00Z", "reason": None},
        },
    ]}
    _assert_nonempty_read_budget(counts, state_batches=1)


def test_inventory_observes_committed_publication_changes_on_next_request(
    inventory_http: InventoryHttp,
) -> None:
    client, stores, counts = inventory_http
    client.portal.call(_seed_mixed_inventory, stores)

    before = _get_inventory(client, counts).json()["connectors"][0]
    assert before["publication_status"] == "published"
    _assert_nonempty_read_budget(counts, state_batches=1)

    client.portal.call(stores.publishing.unpublish_connector, before["connector_id"])
    after = _get_inventory(client, counts).json()["connectors"][0]

    assert after == {**before, "publication_status": "unpublished"}
    _assert_nonempty_read_budget(counts, state_batches=1)


def test_inventory_and_detail_use_the_configured_publication_store(
    inventory_http: InventoryHttp,
) -> None:
    client, stores, counts = inventory_http
    client.portal.call(_seed_mixed_inventory, stores)
    root = cast(FastAPI, client.app)
    admin_app = next(
        cast(FastAPI, route.app)
        for route in root.routes if isinstance(route, Mount) and route.path == "/api/admin"
    )
    runtime = client.portal.call(prepared_inmemory_runtime)
    try:
        publishing = client.portal.call(create_connector_publishing_store, runtime.database)
        client.portal.call(publishing.publish_connector, "gamma")

        def get_alternative_publishing_store() -> ConnectorPublishingStore:
            return publishing

        admin_app.dependency_overrides[get_connector_publishing_store] = get_alternative_publishing_store
        listing = _get_inventory(client, counts).json()["connectors"]
        detail = client.get("/api/admin/connectors/mcp/gamma")
        assert detail.status_code == 200, detail.text
        assert listing[-1]["publication_status"] == detail.json()["publication_status"] == "published"
    finally:
        admin_app.dependency_overrides.pop(get_connector_publishing_store, None)
        client.portal.call(runtime.shutdown)
