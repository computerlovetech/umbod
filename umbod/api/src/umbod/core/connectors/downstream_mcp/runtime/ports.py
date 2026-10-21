from typing import Protocol

from umbod.core.capabilities import CapabilityIdentity

from .models import SharedRuntimeConnection


class DownstreamRuntimeUnavailable(Exception):
    pass


class DownstreamRuntimeResolver(Protocol):
    async def resolve(self, identity: CapabilityIdentity) -> SharedRuntimeConnection: ...
