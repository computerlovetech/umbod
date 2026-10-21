from collections.abc import Mapping

from umbod.core.capabilities import CapabilityIdentity

from .models import SharedRuntimeConnection
from .ports import DownstreamRuntimeUnavailable


class InMemoryDownstreamRuntimeResolver:
    def __init__(self, connections: Mapping[CapabilityIdentity, SharedRuntimeConnection]) -> None:
        self._connections = dict(connections)

    async def resolve(self, identity: CapabilityIdentity) -> SharedRuntimeConnection:
        try:
            return self._connections[identity]
        except KeyError as error:
            raise DownstreamRuntimeUnavailable("Downstream capability is not available") from error
