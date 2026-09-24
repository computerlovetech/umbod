from datetime import UTC, datetime
from typing import cast

import pytest

from umbod.core.capabilities import CapabilityCatalog
from umbod.core.connectors.downstream_mcp.catalog import (
    StoreBackedDownstreamCapabilityCatalog,
)
from umbod.core.connectors.downstream_mcp.models import (
    ConnectorDefinitionModel,
    NoAuthConnectorDefinition,
    DiscoveredToolWithOutputSchema,
    DiscoveredToolWithoutOutputSchema,
    ToolCatalogSnapshot,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionFound,
    ConnectorDefinitionList,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
    ToolCatalogFound,
    ToolCatalogStore,
)


class _Definitions:
    def __init__(self, definition: ConnectorDefinitionModel) -> None:
        self._definition = definition

    async def list(self) -> ConnectorDefinitionList:
        return ConnectorDefinitionList(definitions=(self._definition,))

    async def get(self, query: ConnectorIdQuery) -> ConnectorDefinitionFound:
        return ConnectorDefinitionFound(definition=self._definition)


class _Catalogs:
    def __init__(self, snapshot: ToolCatalogSnapshot) -> None:
        self._snapshot = snapshot

    async def get(self, query: ConnectorIdQuery) -> ToolCatalogFound:
        return ToolCatalogFound(snapshot=self._snapshot)


def _catalog(
    tool: DiscoveredToolWithOutputSchema | DiscoveredToolWithoutOutputSchema,
) -> CapabilityCatalog:
    snapshot = ToolCatalogSnapshot(
        connector_id="records",
        discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
        tools=(tool,),
    )
    definition = NoAuthConnectorDefinition(
        connector_id="records",
        display_name="Records",
        endpoint_url="https://records.example/mcp",
    )
    definitions = cast(ConnectorDefinitionStore, _Definitions(definition))
    catalogs = cast(ToolCatalogStore, _Catalogs(snapshot))
    return cast(CapabilityCatalog, StoreBackedDownstreamCapabilityCatalog(definitions, catalogs))


@pytest.mark.asyncio
async def test_downstream_catalog_normalizes_discovered_tool() -> None:
    catalog = _catalog(
        DiscoveredToolWithOutputSchema(
            identity=ToolIdentity(connector_id="records", downstream_name="find/record"),
            title="Find record",
            description="Returns a record",
            input_schema={
                "type": "object",
                "properties": {"record_id": {"type": "integer"}},
            },
            output_schema={"type": "object"},
        )
    )

    capability = (await catalog.list_capabilities())[0]

    assert capability.identity.connector_kind == "downstream_mcp"
    assert capability.identity.connector_id == "records"
    assert capability.identity.capability_key == "find/record"
    assert capability.title == "Find record"
    assert capability.description == "Returns a record"
    assert capability.input_schema == {
        "type": "object",
        "properties": {"record_id": {"type": "integer"}},
    }
    assert capability.output_schema.status == "present"
    assert capability.output_schema.schema_ == {"type": "object"}


@pytest.mark.asyncio
async def test_downstream_catalog_preserves_absent_output_schema() -> None:
    catalog = _catalog(
        DiscoveredToolWithoutOutputSchema(
            identity=ToolIdentity(connector_id="records", downstream_name="find"),
            title="Find record",
            description="",
            input_schema={"type": "object"},
        )
    )

    capability = (await catalog.list_capabilities())[0]

    assert capability.description == "Find record"
    assert capability.output_schema.status == "absent"
