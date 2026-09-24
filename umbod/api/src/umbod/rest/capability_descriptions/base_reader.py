from umbod.core.capabilities.descriptions.domain import CapabilityDescription
from umbod.core.capabilities.descriptions.overrides import (
    CapabilityDescriptionTargetNotFoundError,
    ConnectorCapabilityDescriptionKey,
)
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, ConnectorRegistry
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionFound,
    ConnectorDefinitionStore,
    ConnectorIdQuery,
)
from umbod.core.connectors.openapi.stores import OpenApiConnectorReader


class CompositeConnectorCapabilityBaseDescriptionReader:
    def __init__(
        self,
        native_registry: ConnectorRegistry,
        downstream_store: ConnectorDefinitionStore,
        openapi_reader: OpenApiConnectorReader,
    ) -> None:
        self._native_registry = native_registry
        self._downstream_store = downstream_store
        self._openapi_reader = openapi_reader

    async def read(self, key: ConnectorCapabilityDescriptionKey) -> CapabilityDescription:
        if key.kind == "native":
            definition = self._native_registry.get_connector_definition(
                key.connector_id, ConnectorDefinitionFilter(availability="registered")
            )
            if definition is None:
                raise CapabilityDescriptionTargetNotFoundError(key.connector_id)
            return definition.metadata.capability_description
        if key.kind == "downstream_mcp":
            result = await self._downstream_store.get(
                ConnectorIdQuery(connector_id=key.connector_id)
            )
            if not isinstance(result, ConnectorDefinitionFound):
                raise CapabilityDescriptionTargetNotFoundError(key.connector_id)
            return result.definition.capability_description
        try:
            connector = await self._openapi_reader.get_connector(key.connector_id)
            return connector.capability_description
        except KeyError as error:
            raise CapabilityDescriptionTargetNotFoundError(key.connector_id) from error
