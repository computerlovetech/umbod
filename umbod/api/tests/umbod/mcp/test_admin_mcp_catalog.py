from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import create_autospec

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from umbod.proxies import Model
from umbod.core.administrator.connector_configuration import ConnectorReference
from umbod.core.administrator.connector_configuration.catalog import ConnectorConfigurationCatalog
from umbod.core.capabilities import CapabilityIdentity
from umbod.core.connectors.native.capabilities import NativeCapabilityCatalog
from umbod.core.connectors.native.registry.inmemory import InMemoryConnectorRegistry
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredPrompt, DiscoveredResource, DiscoveredResourceTemplate,
    DiscoveredToolWithoutOutputSchema, NoAuthConnectorDefinition, ToolCatalogSnapshot,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.stores.factory import create_downstream_mcp_stores
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionStore, ToolCatalogStore, ReplaceToolCatalog, SaveConnectorDefinition,
)
from umbod.mcp.administrator.catalog import AdministratorConfigurationCatalog


class EmptyConfiguration(Model):
    pass


@pytest.mark.asyncio
async def test_administrator_catalog_includes_unavailable_registered_native_capabilities() -> None:
    registry = InMemoryConnectorRegistry(
        [{
            "id": identifier,
            "display_name": "Inventory",
            "description": "Inventory connector",
            "capability_description": "Inventory access",
            "extension": {"source": "built-in"},
            "configuration_schema": EmptyConfiguration,
            "tool_name_prefix": "PublicPrefix",
            "tool_descriptions": [{"operation_name": "list_items", "description": "List"}],
            "prompt_descriptions": [{
                "name": "summary", "description": "Inventory summary", "arguments": (),
            }],
            "resource_descriptions": [
                {"name": "Fixed", "uri": "data://inventory", "description": "Fixed"},
                {"name": "Template", "uri": "data://inventory/{item}", "description": "Template"},
            ],
        } for identifier in ("inventory", "other")],
        [],
    )
    catalog: ConnectorConfigurationCatalog = AdministratorConfigurationCatalog(
        lambda: registry,
        create_autospec(OpenApiConnectorStore),
        create_autospec(ConnectorDefinitionStore),
        create_autospec(ToolCatalogStore),
    )
    connector = ConnectorReference(connector_kind="native", connector_id="inventory")
    assert await catalog.has_connector(connector)
    assert await catalog.list_capabilities(connector) == tuple(
        CapabilityIdentity(
            connector_kind="native", connector_id="inventory",
            capability_kind=kind, capability_key=key,
        ) for kind, key in (
            ("tool", "list_items"), ("prompt", "summary"),
            ("resource", "data://inventory"), ("resource_template", "data://inventory/{item}"),
        )
    )
    assert await NativeCapabilityCatalog.from_registry(registry).list_capabilities() == ()
    missing = ConnectorReference(connector_kind="native", connector_id="missing")
    assert not await catalog.has_connector(missing)
    assert await catalog.list_capabilities(missing) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot_present", [True, False])
async def test_administrator_catalog_reads_only_requested_persisted_downstream_snapshot(
    tmp_path: Path, snapshot_present: bool,
) -> None:
    runtime = await prepared_sqlite_runtime(tmp_path / "catalog.sqlite")
    stores = await create_downstream_mcp_stores("test-secret", runtime.database)
    for identifier in ("inventory", "other"):
        await stores.definitions.save(SaveConnectorDefinition(definition=NoAuthConnectorDefinition(
            connector_id=identifier, display_name=identifier, tool_name_prefix="PublicPrefix",
            endpoint_url=f"https://{identifier}.example.test/mcp",
        )))
        if identifier == "inventory" and not snapshot_present:
            continue
        await stores.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(
            connector_id=identifier, discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
            tools=(DiscoveredToolWithoutOutputSchema(
                identity=ToolIdentity(connector_id=identifier, downstream_name="list_items"),
                title="List", description="List items", input_schema={"type": "object"},
            ),),
            prompts=(DiscoveredPrompt(name="summary", title="Summary", description="Summary", arguments=()),),
            resources=(DiscoveredResource(name="Fixed", title="Fixed", uri="data://inventory", description="Fixed"),),
            resource_templates=(DiscoveredResourceTemplate(name="Template", title="Template", uri_template="data://inventory/{item}", description="Template"),),
        )))
    stores = await create_downstream_mcp_stores("test-secret", runtime.database)
    catalog: ConnectorConfigurationCatalog = AdministratorConfigurationCatalog(
        lambda: InMemoryConnectorRegistry([], []), create_autospec(OpenApiConnectorStore),
        stores.definitions, stores.catalogs,
    )
    connector = ConnectorReference(connector_kind="downstream_mcp", connector_id="inventory")
    assert await catalog.has_connector(connector)
    expected = tuple(
        CapabilityIdentity(
            connector_kind="downstream_mcp", connector_id="inventory",
            capability_kind=kind, capability_key=key,
        ) for kind, key in (
            ("tool", "list_items"), ("prompt", "summary"),
            ("resource", "data://inventory"), ("resource_template", "data://inventory/{item}"),
        )
    ) if snapshot_present else ()
    assert await catalog.list_capabilities(connector) == expected
    assert not await stores.publishing.is_published("inventory")
