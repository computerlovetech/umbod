from typing import Protocol

from umbod.core.identity import ConnectorIdentity


class DownstreamConnectorIdGenerator(Protocol):
    def new_id(self) -> str: ...


class ConnectorIdentityAvailability(Protocol):
    async def ensure_available(self, requested: ConnectorIdentity) -> None: ...
