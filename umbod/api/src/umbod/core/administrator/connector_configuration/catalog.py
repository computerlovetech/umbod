from typing import Protocol

from umbod.core.capabilities import CapabilityIdentity
from .models import ConnectorReference


class ConnectorConfigurationCatalog(Protocol):
    async def has_connector(self, connector: ConnectorReference) -> bool: ...

    async def list_capabilities(
        self, connector: ConnectorReference
    ) -> tuple[CapabilityIdentity, ...]: ...
