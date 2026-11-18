import pytest

from umbod.core.administrator.connector_configuration.models import ConnectorReference
from umbod.core.administrator import ConnectorInventory, ConnectorInventoryEntry
from umbod.core.administrator.connector_inventory import CatalogConnectorInventory
from umbod.core.connectors.downstream_mcp.catalog.definitions import InMemoryConnectorDefinitionReader
from umbod.core.connectors.downstream_mcp.models import (
    OAuthConnectorDefinition,
    StaticBearerConnectorDefinition,
)
from umbod.core.connectors.downstream_mcp.stores.ports import ConnectorDefinitionList
from umbod.core.connectors.native.registry import InMemoryConnectorRegistry
from umbod.core.connectors.openapi.management.models import OpenApiConnector
from umbod.core.publishing.stores.reads import PublicationReadState
from umbod.core.publishing.stores.schema import PublicationStateRecord
from umbod.proxies import Model


class _OpenApiReader:
    def __init__(self, connectors: tuple[OpenApiConnector, ...]) -> None:
        self._connectors = connectors

    async def list_connectors(self) -> tuple[OpenApiConnector, ...]:
        return self._connectors

    async def get_connector(self, connector_id: str) -> OpenApiConnector:
        raise AssertionError(f"Unexpected individual lookup: {connector_id}")


@pytest.mark.asyncio
async def test_inventory_projects_all_connector_kinds_in_kind_and_id_order() -> None:
    inventory: ConnectorInventory = CatalogConnectorInventory(
        native_registry=InMemoryConnectorRegistry(
            [
                {
                    "id": "native-z",
                    "display_name": "Unavailable Native",
                    "description": "Not currently available",
                    "capability_description": "Access connector capabilities.",
                    "extension": {"source": "built-in"},
                    "configuration_schema": Model,
                },
            ],
            [],
        ),
        openapi_reader=_OpenApiReader(
            (
                OpenApiConnector(
                    connector_id="openapi-a",
                    display_name="OpenAPI Example",
                    tool_name_prefix="example",
                    capability_description="Access example capabilities.",
                    created_at="2026-01-01T00:00:00Z",
                    updated_at="2026-01-01T00:00:00Z",
                    icon_url="https://example.test/icon.png",
                ),
            )
        ),
        downstream_reader=InMemoryConnectorDefinitionReader(
            ConnectorDefinitionList(
                definitions=(
                    StaticBearerConnectorDefinition(
                        connector_id="shared-a",
                        display_name="Shared Example",
                        tool_name_prefix="shared_example",
                        capability_description="Access shared capabilities.",
                        endpoint_url="https://shared.example.test/mcp",
                        public_path="/mcp/proxies/shared-a",
                        header_type="custom",
                        custom_header_name="X-Access-Token",
                    ),
                    OAuthConnectorDefinition(
                        connector_id="personal-z",
                        display_name="Personal Example",
                        tool_name_prefix="personal_example",
                        capability_description="Access personal capabilities.",
                        endpoint_url="https://personal.example.test/mcp",
                        public_path="/mcp/proxies/personal-z",
                        authorization_mode="personal",
                    ),
                )
            )
        ),
        publication_reader=PublicationReadState(
            (
                PublicationStateRecord(
                    connector_id="personal-z",
                    published=True,
                    previously_published=True,
                    revision=1,
                    updated_at="2026-01-01T00:00:00Z",
                ),
                PublicationStateRecord(
                    connector_id="native-z",
                    published=False,
                    previously_published=True,
                    revision=2,
                    updated_at="2026-01-01T00:00:00Z",
                ),
            )
        ),
    )

    assert await inventory.list_connectors() == (
        ConnectorInventoryEntry(
            connector=ConnectorReference(connector_kind="downstream_mcp", connector_id="personal-z"),
            display_name="Personal Example",
            publication_state="published",
            authorization_mode="personal",
        ),
        ConnectorInventoryEntry(
            connector=ConnectorReference(connector_kind="downstream_mcp", connector_id="shared-a"),
            display_name="Shared Example",
            publication_state="unpublished",
            authorization_mode="shared",
        ),
        ConnectorInventoryEntry(
            connector=ConnectorReference(connector_kind="native", connector_id="native-z"),
            display_name="Unavailable Native",
            publication_state="unpublished",
            authorization_mode="shared",
        ),
        ConnectorInventoryEntry(
            connector=ConnectorReference(connector_kind="openapi", connector_id="openapi-a"),
            display_name="OpenAPI Example",
            publication_state="unpublished",
            authorization_mode="shared",
        ),
    )


@pytest.mark.asyncio
async def test_inventory_returns_empty_tuple_when_no_connectors_are_registered() -> None:
    inventory: ConnectorInventory = CatalogConnectorInventory(
        native_registry=InMemoryConnectorRegistry([], []),
        openapi_reader=_OpenApiReader(()),
        downstream_reader=InMemoryConnectorDefinitionReader(ConnectorDefinitionList(definitions=())),
        publication_reader=PublicationReadState(()),
    )

    assert await inventory.list_connectors() == ()
