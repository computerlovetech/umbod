from collections.abc import Mapping

from umbod.proxies import Model

from umbod.core.configuration.exceptions import (
    UnknownConnectorConfigurationError,
)
from umbod.core.configuration.ports import ConnectorConfigurationRegistryProtocol


class ConnectorConfigurationRegistry:
    def __init__(self, schemas: Mapping[str, type[Model]]) -> None:
        self._schemas = dict(schemas)

    def get_schema(self, connector_id: str) -> type[Model]:
        schema = self._schemas.get(connector_id)
        if schema is None:
            raise UnknownConnectorConfigurationError(connector_id)
        return schema


__all__ = [
    "ConnectorConfigurationRegistry",
    "ConnectorConfigurationRegistryProtocol",
]
