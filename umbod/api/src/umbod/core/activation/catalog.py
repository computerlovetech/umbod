from umbod.core.activation.domain import (
    ActivationFilter,
    ActivationListFilter,
    ActivationStore,
    CapabilityActivationState,
    CapabilityRef,
)
from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.capabilities.catalog import (
    CapabilityCatalog,
    CapabilityNotFoundError,
)
from umbod.core.capabilities.domain import CapabilityIdentity
from umbod.core.invocation import ConnectorKind


class CapabilitySourceActivationCatalog:
    def __init__(
        self,
        capabilities: CapabilityCatalog,
        store: ActivationStore,
        connector_kind: ConnectorKind,
    ) -> None:
        self._capabilities = capabilities
        self._store = store
        self._connector_kind = connector_kind

    async def list_activations(
        self,
        connector_id: str,
        capability_kind: CapabilityKind,
        filters: ActivationListFilter,
    ) -> tuple[CapabilityActivationState, ...]:
        states = tuple(
            [
                CapabilityActivationState(
                    ref=_ref(
                        self._connector_kind,
                        connector_id,
                        capability_kind,
                        capability.identity.capability_key,
                    ),
                    activation_status=await self._store.get_status(
                        _ref(
                            self._connector_kind,
                            connector_id,
                            capability_kind,
                            capability.identity.capability_key,
                        )
                    ),
                )
                for capability in await self._capabilities.list_capabilities()
                if capability.identity.connector_kind == self._connector_kind
                and capability.identity.connector_id == connector_id
                and capability.identity.capability_kind == capability_kind
            ]
        )
        if filters.activation_status == ActivationFilter.ALL:
            return states
        return tuple(
            state
            for state in states
            if state.activation_status.value == filters.activation_status.value
        )

    async def has_connector(self, connector_id: str) -> bool:
        return any(
            capability.identity.connector_kind == self._connector_kind
            and capability.identity.connector_id == connector_id
            for capability in await self._capabilities.list_capabilities()
        )

    async def has_capability(self, ref: CapabilityRef) -> bool:
        if ref.connector_kind != self._connector_kind:
            return False
        identity = CapabilityIdentity(
            connector_kind=ref.connector_kind,
            connector_id=ref.connector_id,
            capability_kind=ref.capability_kind,
            capability_key=ref.capability_key,
        )
        try:
            await self._capabilities.resolve(identity)
        except CapabilityNotFoundError:
            return False
        return True


class KeySetActivationCatalog:
    def __init__(
        self,
        store: ActivationStore,
        connector_kind: ConnectorKind,
        connectors: dict[str, dict[CapabilityKind, tuple[str, ...]]],
    ) -> None:
        self._store = store
        self._connector_kind = connector_kind
        self._connectors = connectors

    async def list_activations(
        self,
        connector_id: str,
        capability_kind: CapabilityKind,
        filters: ActivationListFilter,
    ) -> tuple[CapabilityActivationState, ...]:
        keys = self._connectors.get(connector_id, {}).get(capability_kind, ())
        states = tuple(
            [
                CapabilityActivationState(
                    ref=_ref(self._connector_kind, connector_id, capability_kind, key),
                    activation_status=await self._store.get_status(
                        _ref(self._connector_kind, connector_id, capability_kind, key)
                    ),
                )
                for key in keys
            ]
        )
        if filters.activation_status == ActivationFilter.ALL:
            return states
        return tuple(
            state
            for state in states
            if state.activation_status.value == filters.activation_status.value
        )

    async def has_connector(self, connector_id: str) -> bool:
        return connector_id in self._connectors

    async def has_capability(self, ref: CapabilityRef) -> bool:
        if ref.connector_kind != self._connector_kind:
            return False
        keys = self._connectors.get(ref.connector_id, {}).get(ref.capability_kind, ())
        return ref.capability_key in keys


def _ref(
    connector_kind: ConnectorKind,
    connector_id: str,
    capability_kind: CapabilityKind,
    capability_key: str,
) -> CapabilityRef:
    return CapabilityRef(
        connector_kind=connector_kind,
        connector_id=connector_id,
        capability_kind=capability_kind,
        capability_key=capability_key,
    )
