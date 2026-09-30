from typing import Protocol

from umbod.core.capabilities import CapabilityIdentity
from .models import ConnectorReference


class ConnectorConfigurationCatalog(Protocol):
    async def has_connector(self, connector: ConnectorReference) -> bool: ...

    async def list_capabilities(
        self, connector: ConnectorReference
    ) -> tuple[CapabilityIdentity, ...]: ...


class InMemoryConnectorConfigurationCatalog:
    def __init__(
        self,
        connectors: tuple[ConnectorReference, ...],
        capabilities: tuple[CapabilityIdentity, ...],
    ) -> None:
        self._connectors = connectors
        self._capabilities = capabilities

    async def has_connector(self, connector: ConnectorReference) -> bool:
        return connector in self._connectors

    async def list_capabilities(
        self, connector: ConnectorReference
    ) -> tuple[CapabilityIdentity, ...]:
        return tuple(
            identity
            for identity in self._capabilities
            if identity.connector_kind == connector.connector_kind
            and identity.connector_id == connector.connector_id
        )
