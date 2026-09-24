from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from umbod.core.capabilities.domain import CapabilityKind
from umbod.core.invocation import ConnectorKind


class ActivationStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class ActivationFilter(str, Enum):
    ALL = "all"
    ENABLED = "enabled"
    DISABLED = "disabled"


class ActivationError(str, Enum):
    CONNECTOR_NOT_FOUND = "connector_not_found"
    CAPABILITY_NOT_FOUND = "capability_not_found"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class CapabilityRef:
    connector_kind: ConnectorKind
    connector_id: str
    capability_kind: CapabilityKind
    capability_key: str


@dataclass(frozen=True)
class ActivationListFilter:
    activation_status: ActivationFilter = ActivationFilter.ALL


@dataclass(frozen=True)
class CapabilityActivationState:
    ref: CapabilityRef
    activation_status: ActivationStatus


@dataclass(frozen=True)
class ActivationFailure:
    error: ActivationError
    message: str


@dataclass(frozen=True)
class ActivationResult:
    state: CapabilityActivationState | None
    failure: ActivationFailure | None


@dataclass(frozen=True)
class ActivationBatchResult:
    states: tuple[CapabilityActivationState, ...]
    changed_states: tuple[CapabilityActivationState, ...]
    failure: ActivationFailure | None


class ActivationStore(Protocol):
    async def get_status(self, ref: CapabilityRef) -> ActivationStatus: ...

    async def set_status(self, ref: CapabilityRef, status: ActivationStatus) -> None: ...

    async def set_statuses(self, states: tuple[CapabilityActivationState, ...]) -> None: ...

    async def reconcile(
        self,
        connector_kind: ConnectorKind,
        connector_id: str,
        capability_kind: CapabilityKind,
        current_keys: tuple[str, ...],
    ) -> None: ...


class ActivationCatalog(Protocol):
    async def list_activations(
        self,
        connector_id: str,
        capability_kind: CapabilityKind,
        filters: ActivationListFilter,
    ) -> tuple[CapabilityActivationState, ...]: ...

    async def has_connector(self, connector_id: str) -> bool: ...

    async def has_capability(self, ref: CapabilityRef) -> bool: ...


class ActivationPort(Protocol):
    async def list_activations(
        self,
        connector_id: str,
        capability_kind: CapabilityKind,
        filters: ActivationListFilter,
    ) -> tuple[CapabilityActivationState, ...]: ...

    async def enable(self, ref: CapabilityRef) -> ActivationResult: ...

    async def disable(self, ref: CapabilityRef) -> ActivationResult: ...

    async def set_statuses(
        self,
        states: tuple[CapabilityActivationState, ...],
    ) -> ActivationBatchResult: ...


class ActivationNotifier(Protocol):
    def activation_changed(self, state: CapabilityActivationState) -> None: ...
