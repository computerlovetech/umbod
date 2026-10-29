from umbod.core.activation.domain import (
    ActivationBatchResult,
    ActivationCatalog,
    ActivationError,
    ActivationFailure,
    ActivationListFilter,
    ActivationNotifier,
    ActivationResult,
    ActivationStatus,
    ActivationStore,
    CapabilityActivationState,
    CapabilityRef,
)
from umbod.core.capabilities.domain import CapabilityKind


class InMemoryActivationNotifier:
    def __init__(self) -> None:
        self.changed_states: list[CapabilityActivationState] = []

    def activation_changed(self, state: CapabilityActivationState) -> None:
        self.changed_states.append(state)


class CapabilityActivationService:
    def __init__(
        self,
        catalog: ActivationCatalog,
        store: ActivationStore,
        notifier: ActivationNotifier,
    ) -> None:
        self._catalog = catalog
        self._store = store
        self._notifier = notifier

    async def list_activations(
        self,
        connector_id: str,
        capability_kind: CapabilityKind,
        filters: ActivationListFilter,
    ) -> tuple[CapabilityActivationState, ...]:
        return await self._catalog.list_activations(connector_id, capability_kind, filters)

    async def enable(self, ref: CapabilityRef) -> ActivationResult:
        return await self._set_status(ref, ActivationStatus.ENABLED)

    async def disable(self, ref: CapabilityRef) -> ActivationResult:
        return await self._set_status(ref, ActivationStatus.DISABLED)

    async def set_statuses(
        self,
        states: tuple[CapabilityActivationState, ...],
    ) -> ActivationBatchResult:
        connector_id = states[0].ref.connector_id
        if not await self._catalog.has_connector(connector_id):
            return ActivationBatchResult(
                states=(),
                changed_states=(),
                failure=ActivationFailure(
                    error=ActivationError.CONNECTOR_NOT_FOUND,
                    message=f"Connector '{connector_id}' was not found.",
                ),
            )
        for state in states:
            if not await self._catalog.has_capability(state.ref):
                return ActivationBatchResult(
                    states=(),
                    changed_states=(),
                    failure=ActivationFailure(
                        error=ActivationError.CAPABILITY_NOT_FOUND,
                        message=(
                            f"Capability '{state.ref.capability_kind}/{state.ref.capability_key}' "
                            f"was not found on connector '{connector_id}'."
                        ),
                    ),
                )
        changed_states = tuple(
            [
                state
                for state in states
                if await self._store.get_status(state.ref) != state.activation_status
            ]
        )
        await self._store.set_statuses(states)
        for state in changed_states:
            self._notifier.activation_changed(state)
        return ActivationBatchResult(
            states=states,
            changed_states=changed_states,
            failure=None,
        )

    async def _set_status(
        self,
        ref: CapabilityRef,
        status: ActivationStatus,
    ) -> ActivationResult:
        if not await self._catalog.has_connector(ref.connector_id):
            return ActivationResult(
                state=None,
                failure=ActivationFailure(
                    error=ActivationError.CONNECTOR_NOT_FOUND,
                    message=f"Connector '{ref.connector_id}' was not found.",
                ),
            )
        if not await self._catalog.has_capability(ref):
            return ActivationResult(
                state=None,
                failure=ActivationFailure(
                    error=ActivationError.CAPABILITY_NOT_FOUND,
                    message=(
                        f"Capability '{ref.capability_kind}/{ref.capability_key}' "
                        f"was not found on connector '{ref.connector_id}'."
                    ),
                ),
            )
        await self._store.set_status(ref, status)
        state = CapabilityActivationState(ref=ref, activation_status=status)
        self._notifier.activation_changed(state)
        return ActivationResult(state=state, failure=None)
