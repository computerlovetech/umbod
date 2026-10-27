from umbod.core.capabilities import CapabilityAvailability, CapabilityIdentity, NormalizedCapability
from umbod.core.capabilities.catalog import CapabilityCatalog
from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionKey,
    ConnectorCapabilityDescriptionOverrideStore,
    OverriddenCapabilityDescription,
)
from umbod.core.permissions.domain import ConnectorCapabilityRef
from umbod.core.permissions.ports import GroupPermissionLookup

from .models import CatalogueCapability, CatalogueConnector, CatalogueToolCapability


class ExplicitCapabilityPermissions:
    def __init__(self, permissions: GroupPermissionLookup, groups: tuple[str, ...]) -> None:
        self._permissions = permissions
        self._groups = groups

    async def allows(self, identity: CapabilityIdentity) -> bool:
        target = ConnectorCapabilityRef(
            identity.connector_id, identity.capability_kind, identity.capability_key,
        )
        for group in self._groups:
            if target in (await self._permissions.list_group_permissions(group)).capabilities:
                return True
        return False


class IndexedCapabilityPermissions:
    def __init__(self, capabilities: frozenset[ConnectorCapabilityRef]) -> None:
        self._capabilities = capabilities

    @classmethod
    async def capture(
        cls, permissions: GroupPermissionLookup, groups: tuple[str, ...],
    ) -> "IndexedCapabilityPermissions":
        capabilities: set[ConnectorCapabilityRef] = set()
        for group in dict.fromkeys(groups):
            capabilities.update((await permissions.list_group_permissions(group)).capabilities)
        return cls(frozenset(capabilities))

    async def allows(self, identity: CapabilityIdentity) -> bool:
        return ConnectorCapabilityRef(
            identity.connector_id, identity.capability_kind, identity.capability_key,
        ) in self._capabilities


class SharedCatalogueSource:
    def __init__(
        self, catalog: CapabilityCatalog, availability: CapabilityAvailability,
        descriptions: ConnectorCapabilityDescriptionOverrideStore,
    ) -> None:
        self._catalog = catalog
        self._availability = availability
        self._descriptions = descriptions

    async def list_connectors(self) -> tuple[CatalogueConnector, ...]:
        connectors: dict[tuple[str, str], CatalogueConnector] = {}
        for capability in await self._catalog.list_capabilities():
            identity = capability.identity
            if not await self._availability.is_available(identity):
                continue
            key = (identity.connector_kind, identity.connector_id)
            summary = CatalogueToolCapability(
                kind="tool", key=identity.capability_key,
                name=capability.title, description=capability.description,
                input_schema=capability.input_schema, output_schema=capability.output_schema,
            ) if identity.capability_kind == "tool" else CatalogueCapability(
                kind=identity.capability_kind, key=identity.capability_key,
                name=capability.title, description=capability.description,
            )
            if key not in connectors:
                connectors[key] = await self._connector(capability)
            current = connectors[key]
            connectors[key] = current.model_copy(update={"capabilities": current.capabilities + (summary,)})
        return tuple(
            connector.model_copy(update={"capabilities": tuple(sorted(
                connector.capabilities, key=lambda item: (item.kind, item.key),
            ))})
            for connector in connectors.values()
        )

    async def _connector(self, capability: NormalizedCapability) -> CatalogueConnector:
        identity = capability.identity
        override = await self._descriptions.get(ConnectorCapabilityDescriptionKey(
            kind=identity.connector_kind, connector_id=identity.connector_id,
        ))
        description = (
            override.description if isinstance(override, OverriddenCapabilityDescription)
            else capability.connector_capability_description
        )
        return CatalogueConnector(
            connector_id=identity.connector_id, kind=identity.connector_kind,
            display_name=capability.connector_display_name,
            capability_description=description, ownership="shared", capabilities=(),
        )
