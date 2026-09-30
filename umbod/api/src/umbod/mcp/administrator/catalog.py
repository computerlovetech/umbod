from collections.abc import Callable

from umbod.core.administrator.connector_configuration import ConnectorReference
from umbod.core.capabilities import CapabilityIdentity
from umbod.core.connectors.native.capabilities import NativeCapabilityCatalog
from umbod.core.connectors.native.registry import (
    ConnectorDefinitionFilter,
    ConnectorRegistry,
)
from umbod.core.connectors.openapi.administrator_catalog import OpenApiConfigurationCatalog
from umbod.core.connectors.openapi.stores import OpenApiConnectorStore
from umbod.core.connectors.downstream_mcp.catalog import (
    StoreBackedDownstreamCapabilityCatalog,
)
from umbod.core.connectors.downstream_mcp.stores.ports import (
    ConnectorDefinitionFound,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
    ToolCatalogStore,
)


class AdministratorConfigurationCatalog:
    def __init__(
        self,
        native: Callable[[], ConnectorRegistry],
        openapi: OpenApiConnectorStore,
        downstream_definitions: ConnectorDefinitionStore,
        downstream_catalogs: ToolCatalogStore,
    ) -> None:
        self._native = native
        self._openapi = openapi
        self._downstream_definitions = downstream_definitions
        self._openapi_catalog = OpenApiConfigurationCatalog(openapi)
        self._downstream_catalog = StoreBackedDownstreamCapabilityCatalog(
            downstream_definitions, downstream_catalogs
        )

    async def has_connector(self, connector: ConnectorReference) -> bool:
        if connector.connector_kind == "native":
            return self._native().get_connector_definition(
                connector.connector_id,
                ConnectorDefinitionFilter(availability="registered"),
            ) is not None
        if connector.connector_kind == "openapi":
            return any(
                definition.connector_id == connector.connector_id
                for definition in await self._openapi.list_connectors()
            )
        return isinstance(
            await self._downstream_definitions.get(
                ConnectorIdQuery(connector_id=connector.connector_id)
            ),
            ConnectorDefinitionFound,
        )

    async def list_capabilities(
        self, connector: ConnectorReference
    ) -> tuple[CapabilityIdentity, ...]:
        if connector.connector_kind == "openapi":
            return await self._openapi_catalog.list_capabilities(connector)
        if connector.connector_kind == "native":
            definition = self._native().get_connector_definition(
                connector.connector_id,
                ConnectorDefinitionFilter(availability="registered"),
            )
            if definition is None:
                return ()
            capabilities = await NativeCapabilityCatalog.from_definition(
                definition
            ).list_capabilities()
        else:
            capabilities = await self._downstream_catalog.list_connector_capabilities(
                connector.connector_id
            )
        return tuple(capability.identity for capability in capabilities)
