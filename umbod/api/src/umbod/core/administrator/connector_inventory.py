from umbod.core.administrator.connector_configuration.models import ConnectorReference
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.stores.ports import ConnectorDefinitionReader
from umbod.core.connectors.native.registry import (
    ConnectorDefinitionFilter,
    ConnectorRegistry,
)
from umbod.core.connectors.openapi.stores.ports import OpenApiConnectorReader
from umbod.core.publishing import ConnectorPublicationReader, PublishState

from .models import ConnectorInventoryEntry


class CatalogConnectorInventory:
    def __init__(
        self,
        native_registry: ConnectorRegistry,
        openapi_reader: OpenApiConnectorReader,
        downstream_reader: ConnectorDefinitionReader,
        publication_reader: ConnectorPublicationReader,
    ) -> None:
        self._native_registry = native_registry
        self._openapi_reader = openapi_reader
        self._downstream_reader = downstream_reader
        self._publication_reader = publication_reader

    async def list_connectors(self) -> tuple[ConnectorInventoryEntry, ...]:
        entries = await self._list_native()
        entries.extend(await self._list_openapi())
        entries.extend(await self._list_downstream())
        entries.sort(
            key=lambda entry: (
                entry.connector.connector_kind,
                entry.connector.connector_id,
            )
        )
        return tuple(entries)

    async def _list_native(self) -> list[ConnectorInventoryEntry]:
        definitions = self._native_registry.list_connector_definitions(
            ConnectorDefinitionFilter(availability="registered")
        )
        return [
            ConnectorInventoryEntry(
                connector=ConnectorReference(
                    connector_kind="native", connector_id=item.metadata.id
                ),
                display_name=item.metadata.display_name,
                publication_state=await self._publication_state(item.metadata.id),
                authorization_mode="shared",
            )
            for item in definitions
        ]

    async def _list_openapi(self) -> list[ConnectorInventoryEntry]:
        return [
            ConnectorInventoryEntry(
                connector=ConnectorReference(
                    connector_kind="openapi", connector_id=item.connector_id
                ),
                display_name=item.display_name,
                publication_state=await self._publication_state(item.connector_id),
                authorization_mode="shared",
            )
            for item in await self._openapi_reader.list_connectors()
        ]

    async def _list_downstream(self) -> list[ConnectorInventoryEntry]:
        definitions = await self._downstream_reader.list()
        return [
            ConnectorInventoryEntry(
                connector=ConnectorReference(
                    connector_kind="downstream_mcp", connector_id=item.connector_id
                ),
                display_name=item.display_name,
                publication_state=await self._publication_state(item.connector_id),
                authorization_mode="personal"
                if uses_personal_oauth(item)
                else "shared",
            )
            for item in definitions.definitions
        ]

    async def _publication_state(self, connector_id: str) -> PublishState:
        if await self._publication_reader.is_published(connector_id):
            return "published"
        return "unpublished"
