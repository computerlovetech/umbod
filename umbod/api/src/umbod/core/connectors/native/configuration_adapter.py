from umbod.core.configuration.exceptions import (
    UnknownConnectorConfigurationError,
)
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter


class ConnectorConfigurationSchemaRegistryAdapter:
    def __init__(self, registry: object) -> None:
        self._registry = registry

    def get_schema(self, connector_id: str) -> object:
        get_connector_definition = getattr(self._registry, "get_connector_definition")
        connector_definition = get_connector_definition(
            connector_id, ConnectorDefinitionFilter(availability="available")
        )
        if connector_definition is None:
            raise UnknownConnectorConfigurationError(connector_id)
        return connector_definition.configuration_schema


__all__ = ["ConnectorConfigurationSchemaRegistryAdapter"]
