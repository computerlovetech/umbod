from asyncio import Lock
from typing import Protocol

from fastmcp import FastMCP

from umbod.core.capabilities import (
    CapabilityAvailability,
    CapabilityIdentity,
    ConnectorStoreCapabilityActivation,
    ConnectorStoreCapabilityPublication,
    CapabilityNotFoundError,
    NormalizedCapability,
    UnrestrictedCapabilityPermissionPolicy,
    UnrestrictedCapabilityReadiness,
)
from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionKey,
    OverriddenCapabilityDescription,
)
from umbod.core.connectors.openapi.catalog import StoreBackedOpenApiCapabilityCatalog
from umbod.core.permissions.domain import ConnectorToolRef
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.mcp.connectors.openapi.deps import get_openapi_connector_store


class OpenApiDiscoveryProjection(Protocol):
    def snapshot(self) -> tuple[NormalizedCapability, ...]: ...

    async def reconcile(self, server: FastMCP) -> None: ...


class InMemoryOpenApiDiscoveryProjection:
    def __init__(self) -> None:
        self._capabilities: tuple[NormalizedCapability, ...] = ()
        self._reconciliation_lock = Lock()

    def snapshot(self) -> tuple[NormalizedCapability, ...]:
        return tuple(capability.model_copy(deep=True) for capability in self._capabilities)

    async def reconcile(self, server: FastMCP) -> None:
        async with self._reconciliation_lock:
            try:
                capabilities = await self._load(server)
            except Exception:
                self._capabilities = ()
                raise
            self._capabilities = capabilities

    async def _load(self, server: FastMCP) -> tuple[NormalizedCapability, ...]:
        store = await get_openapi_connector_store(server)
        capabilities = await StoreBackedOpenApiCapabilityCatalog(store).list_capabilities()
        connector_ids = tuple(dict.fromkeys(item.identity.connector_id for item in capabilities))
        overrides = await server.capability_description_overrides.get_many(tuple(
            ConnectorCapabilityDescriptionKey(kind="openapi", connector_id=connector_id)
            for connector_id in connector_ids
        ))
        descriptions = {
            connector_id: state.description
            for connector_id, state in zip(connector_ids, overrides, strict=True)
            if isinstance(state, OverriddenCapabilityDescription)
        }
        availability = openapi_discovery_availability(server)
        available: list[NormalizedCapability] = []
        for capability in capabilities:
            if availability is not None and not await availability.is_available(capability.identity):
                continue
            description = descriptions.get(
                capability.identity.connector_id, capability.connector_capability_description
            )
            available.append(capability.model_copy(update={
                "connector_capability_description": description,
            }))
        return tuple(available)


def openapi_discovery_availability(server: FastMCP) -> CapabilityAvailability | None:
    publishing = getattr(server, "openapi_publishing_store", None)
    activation = getattr(server, "capability_activation_store", None)
    if publishing is None or activation is None:
        return None
    return CapabilityAvailability(
        ConnectorStoreCapabilityPublication("openapi", publishing),
        ConnectorStoreCapabilityActivation("openapi", activation),
        UnrestrictedCapabilityReadiness(),
        UnrestrictedCapabilityPermissionPolicy(),
    )


class AuthorizedOpenApiDiscoveryCatalog:
    def __init__(
        self,
        capabilities: tuple[NormalizedCapability, ...],
        permissions: GroupPermissionReader,
        groups: tuple[str, ...],
    ) -> None:
        self._capabilities = tuple(capability.model_copy(deep=True) for capability in capabilities)
        self._permissions = permissions
        self._groups = groups

    async def list_capabilities(self) -> tuple[NormalizedCapability, ...]:
        connectors: set[str] = set()
        operations: set[ConnectorToolRef] = set()
        for group in dict.fromkeys(self._groups):
            grants = await self._permissions.list_group_permissions(group)
            connectors.update(grants.connector_ids)
            operations.update(grants.tools)
        return tuple(
            capability.model_copy(deep=True) for capability in self._capabilities
            if capability.identity.connector_id in connectors
            or ConnectorToolRef(
                capability.identity.connector_id, capability.identity.capability_key
            ) in operations
        )

    async def resolve(self, identity: CapabilityIdentity) -> NormalizedCapability:
        for capability in await self.list_capabilities():
            if capability.identity == identity:
                return capability
        raise CapabilityNotFoundError(identity)


async def initialize_openapi_discovery(server: FastMCP) -> None:
    projection = InMemoryOpenApiDiscoveryProjection()
    server.openapi_discovery_catalog = projection
    await projection.reconcile(server)


async def reconcile_openapi_discovery(server: FastMCP) -> None:
    projection: OpenApiDiscoveryProjection = server.openapi_discovery_catalog
    await projection.reconcile(server)
