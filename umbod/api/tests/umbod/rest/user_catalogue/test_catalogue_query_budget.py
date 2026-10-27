from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount

from tests.persistence_runtime import prepared_inmemory_runtime, prepared_sqlite_runtime
from tests.umbod.rest.user_catalogue.query_budget_support import CountingRuntime, QueryCounts
from umbod.config import AppConfig
from umbod.core.activation import ActivationStatus, CapabilityActivationState, CapabilityRef
from umbod.core.activation.stores.schema import CAPABILITY_ACTIVATION_STATE_TABLE
from umbod.core.connectors.downstream_mcp.adapters.settings import downstream_mcp_infrastructure_settings_from_app_config
from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredToolWithoutOutputSchema,
    NoAuthConnectorDefinition,
    NoAuthCredentialState,
    ToolCatalogSnapshot,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.stores import (
    CONNECTOR_CREDENTIAL_TABLE,
    CONNECTOR_DEFINITION_TABLE,
    TOOL_CATALOG_TABLE,
    ReplaceToolCatalog,
    SaveConnectorDefinition,
    SaveCredential,
    create_downstream_mcp_stores,
)
from umbod.core.permissions.domain import ConnectorCapabilityRef, SaveGroupPermissionsRequest
from umbod.core.permissions.stores.schema import CAPABILITY_PERMISSION_TABLE, CONNECTOR_PERMISSION_TABLE
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.user_catalogue import UserCatalogue
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app


class CatalogueVerifier:
    def verify(self, token: str) -> JwtClaims:
        return JwtClaims(claims={"iss": "issuer", "sub": "reader", "groups": ["readers"]})


@pytest.fixture(params=["inmemory", "sqlite"])
def catalogue_http(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, ConnectorApiDependencyFactories, QueryCounts]]:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}')
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        rest={"metrics_enabled": False},
        connector_store={"type": "inmemory"},
        admin_authentication={"mode": "simulation", "environment": "development"},
        personal_connections={"enabled": False},
    )
    root = create_app(settings, [], user_verifier=CatalogueVerifier())
    app = next(route.app for route in root.routes if isinstance(route, Mount) and route.path == "/api/me")
    with TestClient(root, headers={"Authorization": "Bearer reader"}) as client:
        runtime = (
            client.portal.call(prepared_inmemory_runtime)
            if request.param == "inmemory"
            else client.portal.call(prepared_sqlite_runtime, tmp_path / "catalogue.sqlite")
        )
        counts = QueryCounts()
        wrapped_runtime = CountingRuntime(runtime, counts)
        factories = ConnectorApiDependencyFactories.from_settings(settings, wrapped_runtime, [])

        def catalogue_factories() -> ConnectorApiDependencyFactories:
            return factories

        app.dependency_overrides[get_connector_api_dependency_factories] = catalogue_factories
        try:
            yield client, factories, counts
        finally:
            app.dependency_overrides.clear()
            client.portal.call(wrapped_runtime.shutdown)


async def seed_shared_tools(factories: ConnectorApiDependencyFactories, tool_count: int) -> None:
    stores = await create_downstream_mcp_stores(
        downstream_mcp_infrastructure_settings_from_app_config(factories.settings).credential_secret,
        factories.persistence_runtime.database,
    )
    await stores.definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(
        connector_id="shared", display_name="Shared", tool_name_prefix="Shared",
        endpoint_url="https://example.invalid/mcp",
    )))
    await stores.credentials.save(SaveCredential(credential=NoAuthCredentialState(connector_id="shared")))
    keys = tuple(f"read_{index}" for index in range(tool_count))
    await stores.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(
        connector_id="shared", discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        tools=tuple(DiscoveredToolWithoutOutputSchema(
            identity=ToolIdentity(connector_id="shared", downstream_name=key),
            title=key, description=key, input_schema={"type": "object"},
        ) for key in keys),
    )))
    await stores.publishing.publish_connector("shared")
    await stores.activations.set_statuses(tuple(CapabilityActivationState(
        ref=CapabilityRef(
            connector_kind="downstream_mcp", connector_id="shared",
            capability_kind="tool", capability_key=key,
        ),
        activation_status=ActivationStatus.ENABLED,
    ) for key in keys))
    permissions = await factories.group_permission_store.create()
    await permissions.save_group_permissions(SaveGroupPermissionsRequest(
        group_id="readers", connector_ids=(),
        capabilities=tuple(ConnectorCapabilityRef(
            connector_id="shared", capability_kind="tool", capability_key=key,
        ) for key in keys),
    ))


def read_catalogue(client: TestClient, counts: QueryCounts) -> UserCatalogue:
    counts.reset()
    response = client.get("/api/me/catalogue")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return UserCatalogue.model_validate(response.json())


def assert_bounded_reads(counts: QueryCounts) -> None:
    for table in (
        PUBLICATION_STATE_TABLE, CAPABILITY_ACTIVATION_STATE_TABLE,
        CONNECTOR_PERMISSION_TABLE, CAPABILITY_PERMISSION_TABLE,
    ):
        assert counts.reads[table.name] == 1, counts.reads
    for table in (CONNECTOR_DEFINITION_TABLE, TOOL_CATALOG_TABLE, CONNECTOR_CREDENTIAL_TABLE):
        assert counts.reads[table.name] <= 1, counts.reads
    assert not counts.writes
    assert counts.schema_calls == 0


def test_shared_catalogue_read_and_session_budgets_do_not_grow_per_tool(
    catalogue_http: tuple[TestClient, ConnectorApiDependencyFactories, QueryCounts],
) -> None:
    client, factories, counts = catalogue_http
    budgets: list[tuple[Counter[str], int]] = []
    for tool_count in (1, 40):
        client.portal.call(seed_shared_tools, factories, tool_count)
        catalogue = read_catalogue(client, counts)
        assert len(catalogue.connectors) == 1
        connector = catalogue.connectors[0]
        assert connector.connector_id == "shared"
        assert connector.kind == "downstream_mcp"
        assert {capability.key for capability in connector.capabilities} == {
            f"read_{index}" for index in range(tool_count)
        }
        assert all(capability.kind == "tool" for capability in connector.capabilities)
        assert_bounded_reads(counts)
        budgets.append((counts.reads.copy(), counts.sessions))
    assert budgets[0] == budgets[1]


async def revoke_shared_grants(factories: ConnectorApiDependencyFactories) -> None:
    permissions = await factories.group_permission_store.create()
    await permissions.save_group_permissions(SaveGroupPermissionsRequest(
        group_id="readers", connector_ids=(), capabilities=(),
    ))


def test_shared_catalogue_observes_committed_grant_revocation_on_next_request(
    catalogue_http: tuple[TestClient, ConnectorApiDependencyFactories, QueryCounts],
) -> None:
    client, factories, counts = catalogue_http
    client.portal.call(seed_shared_tools, factories, 40)
    before = read_catalogue(client, counts)
    assert len(before.connectors) == 1
    assert len(before.connectors[0].capabilities) == 40
    assert_bounded_reads(counts)
    client.portal.call(revoke_shared_grants, factories)
    after = read_catalogue(client, counts)
    assert after.connectors == ()
    assert_bounded_reads(counts)
