from typing import Any

from pydantic import SecretStr
from umbod.proxies import Model

from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.publishing import ConnectorPublishingStore
from umbod.core.connectors.native.registry import ConnectorDefinitionFilter, ConnectorRegistry

from umbod.rest.system.schemas import ConnectorRuntimeStateResponse


class RawConnectorConfigurationSerializer:
    def dump(self, configuration: Model) -> dict[str, object]:
        return {key: self._dump_value(value) for key, value in configuration.model_dump().items()}

    def _dump_value(self, value: Any) -> object:
        if isinstance(value, SecretStr):
            return value.get_secret_value()
        if isinstance(value, dict):
            return {str(key): self._dump_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._dump_value(item) for item in value]
        return value


class ConnectorRuntimeStateService:
    def __init__(
        self,
        connector_registry: ConnectorRegistry,
        configuration_store: ConnectorCurrentConfigurationStore,
        publishing_store: ConnectorPublishingStore,
        configuration_serializer: RawConnectorConfigurationSerializer,
    ) -> None:
        self.connector_registry = connector_registry
        self.configuration_store = configuration_store
        self.publishing_store = publishing_store
        self.configuration_serializer = configuration_serializer

    async def get_runtime_state(self, connector_id: str) -> ConnectorRuntimeStateResponse:
        connector_definition = self.connector_registry.get_connector_definition(
            connector_id, ConnectorDefinitionFilter(availability="registered")
        )
        configuration = await self.configuration_store.get_current_configuration(connector_id)
        serialized_configuration = (
            self.configuration_serializer.dump(configuration) if configuration is not None else None
        )
        return ConnectorRuntimeStateResponse(
            connector_id=connector_id,
            display_name=connector_definition.metadata.display_name
            if connector_definition is not None
            else None,
            available=connector_definition.available if connector_definition is not None else False,
            published=await self.publishing_store.is_published(connector_id),
            configuration=serialized_configuration,
        )
