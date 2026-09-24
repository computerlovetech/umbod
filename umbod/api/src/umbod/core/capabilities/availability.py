from typing import Protocol

from umbod.core.activation.domain import ActivationStatus, ActivationStore, CapabilityRef
from umbod.core.capabilities.catalog import (
    CapabilityCatalog,
    CapabilityNotFoundError,
)
from umbod.core.capabilities.domain import CapabilityIdentity
from umbod.core.invocation import ConnectorKind
from umbod.core.publishing.store import ConnectorPublishingStore


class CapabilityPublication(Protocol):
    async def is_published(self, identity: CapabilityIdentity) -> bool: ...


class CapabilityActivation(Protocol):
    async def is_enabled(self, identity: CapabilityIdentity) -> bool: ...


class CapabilityReadiness(Protocol):
    async def is_ready(self, identity: CapabilityIdentity) -> bool: ...


class CapabilityPermissionPolicy(Protocol):
    async def allows(self, identity: CapabilityIdentity) -> bool: ...


class CapabilityAvailability:
    def __init__(
        self,
        publishing: CapabilityPublication,
        activations: CapabilityActivation,
        readiness: CapabilityReadiness,
        permissions: CapabilityPermissionPolicy,
    ) -> None:
        self._publishing = publishing
        self._activations = activations
        self._readiness = readiness
        self._permissions = permissions

    async def is_available(self, identity: CapabilityIdentity) -> bool:
        if not await self._publishing.is_published(identity):
            return False
        if not await self._activations.is_enabled(identity):
            return False
        if not await self._permissions.allows(identity):
            return False
        return await self._readiness.is_ready(identity)


class ConnectorStoreCapabilityPublication:
    def __init__(
        self,
        connector_kind: ConnectorKind,
        store: ConnectorPublishingStore,
    ) -> None:
        self._connector_kind = connector_kind
        self._store = store

    async def is_published(self, identity: CapabilityIdentity) -> bool:
        return identity.connector_kind == self._connector_kind and await self._store.is_published(
            identity.connector_id
        )


class ConnectorStoreCapabilityActivation:
    def __init__(
        self,
        connector_kind: ConnectorKind,
        store: ActivationStore,
    ) -> None:
        self._connector_kind = connector_kind
        self._store = store

    async def is_enabled(self, identity: CapabilityIdentity) -> bool:
        if identity.connector_kind != self._connector_kind:
            return False
        status = await self._store.get_status(
            CapabilityRef(
                connector_kind=identity.connector_kind,
                connector_id=identity.connector_id,
                capability_kind=identity.capability_kind,
                capability_key=identity.capability_key,
            )
        )
        return status == ActivationStatus.ENABLED


class CatalogCapabilityReadiness:
    def __init__(self, catalog: CapabilityCatalog) -> None:
        self._catalog = catalog

    async def is_ready(self, identity: CapabilityIdentity) -> bool:
        try:
            await self._catalog.resolve(identity)
        except CapabilityNotFoundError:
            return False
        return True


class AvailabilityAwareCapabilityAuthorizer:
    def __init__(
        self,
        authorizer: object,
        availability: CapabilityAvailability,
        connector_kind: ConnectorKind,
    ) -> None:
        self._authorizer = authorizer
        self._availability = availability
        self._connector_kind = connector_kind

    async def allows(
        self,
        groups: tuple[str, ...],
        connector_id: str,
        operation_id: str,
    ) -> bool:
        identity = CapabilityIdentity(
            connector_kind=self._connector_kind,
            connector_id=connector_id,
            capability_kind="tool",
            capability_key=operation_id,
        )
        if not await self._availability.is_available(identity):
            return False
        return await self._authorizer.allows(groups, connector_id, operation_id)


class UnrestrictedCapabilityPublication:
    async def is_published(self, identity: CapabilityIdentity) -> bool:
        return True


class UnrestrictedCapabilityActivation:
    async def is_enabled(self, identity: CapabilityIdentity) -> bool:
        return True


class UnrestrictedCapabilityReadiness:
    async def is_ready(self, identity: CapabilityIdentity) -> bool:
        return True


class UnrestrictedCapabilityPermissionPolicy:
    async def allows(self, identity: CapabilityIdentity) -> bool:
        return True
