from umbod.core.capabilities.availability import CapabilityReadiness
from umbod.core.capabilities.domain import CapabilityIdentity


class RequestConnectorReadiness:
    def __init__(self, readiness: CapabilityReadiness) -> None:
        self._readiness = readiness
        self._results: dict[tuple[str, str], bool] = {}

    async def is_ready(self, identity: CapabilityIdentity) -> bool:
        key = (identity.connector_kind, identity.connector_id)
        if key not in self._results:
            self._results[key] = await self._readiness.is_ready(identity)
        return self._results[key]
