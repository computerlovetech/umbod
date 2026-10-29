from umbod.core.activation.domain import ActivationStatus, CapabilityActivationState, CapabilityRef
from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.invocation import ConnectorKind


class InMemoryActivationStore:
    def __init__(self) -> None:
        self._statuses: dict[CapabilityRef, ActivationStatus] = {}

    async def get_status(self, ref: CapabilityRef) -> ActivationStatus:
        return self._statuses.get(ref, ActivationStatus.DISABLED)

    async def set_status(self, ref: CapabilityRef, status: ActivationStatus) -> None:
        self._statuses[ref] = status

    async def set_statuses(self, states: tuple[CapabilityActivationState, ...]) -> None:
        for state in states:
            self._statuses[state.ref] = state.activation_status

    async def reconcile(
        self,
        connector_kind: ConnectorKind,
        connector_id: str,
        capability_kind: CapabilityKind,
        current_keys: tuple[str, ...],
    ) -> None:
        current = set(current_keys)
        stale = [
            ref
            for ref in self._statuses
            if ref.connector_kind == connector_kind
            and ref.connector_id == connector_id
            and ref.capability_kind == capability_kind
            and ref.capability_key not in current
        ]
        for ref in stale:
            del self._statuses[ref]
