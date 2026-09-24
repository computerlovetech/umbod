from umbod.core.permissions.domain import (
    AssignableCapabilityPermissionTarget,
    AssignableConnectorPermissionTarget,
    AssignablePermissionTargets,
    ConnectorCapabilityRef,
    ConnectorToolRef,
)
from umbod.core.capabilities import (
    CapabilityActivation,
    CapabilityCatalog,
    CapabilityIdentity,
    CapabilityNotFoundError,
    CapabilityPublication,
    CapabilityReadiness,
    NormalizedCapability,
)
from umbod.core.permissions.ports import AssignablePermissionCatalog


class CapabilityPermissionCatalog:
    def __init__(
        self,
        capabilities: CapabilityCatalog,
        connector_kind: str,
        publication: CapabilityPublication,
        activation: CapabilityActivation,
        readiness: CapabilityReadiness,
        validate_connector_availability: bool,
        validate_tool_availability: bool,
        include_connector_without_tools: bool,
    ) -> None:
        self._capabilities = capabilities
        self._connector_kind = connector_kind
        self._publication = publication
        self._activation = activation
        self._readiness = readiness
        self._validate_connector_availability = validate_connector_availability
        self._validate_tool_availability = validate_tool_availability
        self._include_connector_without_tools = include_connector_without_tools

    async def has_connector(self, connector_id: str) -> bool:
        capabilities = await self._connector_capabilities(connector_id)
        if not self._validate_connector_availability:
            return bool(capabilities)
        return any([await self._is_connector_ready(item.identity) for item in capabilities])

    async def has_capability(self, capability: ConnectorCapabilityRef) -> bool:
        identity = CapabilityIdentity(
            connector_kind=self._connector_kind,
            connector_id=capability.connector_id,
            capability_kind=capability.capability_kind,
            capability_key=capability.capability_key,
        )
        try:
            await self._capabilities.resolve(identity)
        except CapabilityNotFoundError:
            return False
        if not self._validate_tool_availability:
            return True
        return await self._is_assignable(identity)

    async def has_tool(self, tool: ConnectorToolRef) -> bool:
        return await self.has_capability(tool.as_capability())

    async def list_assignable_targets(self) -> AssignablePermissionTargets:
        capabilities = await self._capabilities.list_capabilities()
        connector_targets: dict[str, AssignableConnectorPermissionTarget] = {}
        capability_targets: list[AssignableCapabilityPermissionTarget] = []
        for capability in capabilities:
            if capability.identity.connector_kind != self._connector_kind:
                continue
            if await self._is_assignable(capability.identity):
                capability_targets.append(
                    AssignableCapabilityPermissionTarget(
                        connector_id=capability.identity.connector_id,
                        capability_kind=capability.identity.capability_kind,
                        capability_key=capability.identity.capability_key,
                        display_name=capability.title,
                    )
                )
            if await self._include_connector(capability.identity.connector_id, capability_targets):
                connector_targets[capability.identity.connector_id] = (
                    AssignableConnectorPermissionTarget(
                        connector_id=capability.identity.connector_id,
                        display_name=capability.connector_display_name
                        or capability.identity.connector_id,
                    )
                )
        return _targets(connector_targets, capability_targets)

    async def _include_connector(
        self,
        connector_id: str,
        capabilities: list[AssignableCapabilityPermissionTarget],
    ) -> bool:
        has_capability = any(item.connector_id == connector_id for item in capabilities)
        return has_capability or (
            self._include_connector_without_tools and await self.has_connector(connector_id)
        )

    async def _connector_capabilities(self, connector_id: str) -> tuple[NormalizedCapability, ...]:
        return tuple(
            capability
            for capability in await self._capabilities.list_capabilities()
            if capability.identity.connector_kind == self._connector_kind
            and capability.identity.connector_id == connector_id
        )

    async def _is_connector_ready(self, identity: CapabilityIdentity) -> bool:
        return await self._publication.is_published(identity) and await self._readiness.is_ready(
            identity
        )

    async def _is_assignable(self, identity: CapabilityIdentity) -> bool:
        return (
            await self._publication.is_published(identity)
            and await self._activation.is_enabled(identity)
            and await self._readiness.is_ready(identity)
        )


class CompositeConnectorToolPermissionCatalog:
    def __init__(self, catalogs: tuple[AssignablePermissionCatalog, ...]) -> None:
        self._catalogs = catalogs

    async def has_connector(self, connector_id: str) -> bool:
        return any([await catalog.has_connector(connector_id) for catalog in self._catalogs])

    async def has_capability(self, capability: ConnectorCapabilityRef) -> bool:
        return any([await catalog.has_capability(capability) for catalog in self._catalogs])

    async def has_tool(self, tool: ConnectorToolRef) -> bool:
        return await self.has_capability(tool.as_capability())

    async def list_assignable_targets(self) -> AssignablePermissionTargets:
        connectors: dict[str, AssignableConnectorPermissionTarget] = {}
        capabilities: dict[
            tuple[str, str, str], AssignableCapabilityPermissionTarget
        ] = {}
        for catalog in self._catalogs:
            targets = await catalog.list_assignable_targets()
            _merge_connectors(connectors, targets.connectors)
            _merge_capabilities(capabilities, targets.capabilities)
        return AssignablePermissionTargets(
            connectors=tuple(connectors[key] for key in sorted(connectors)),
            capabilities=tuple(capabilities[key] for key in sorted(capabilities)),
        )


def _targets(
    connectors: dict[str, AssignableConnectorPermissionTarget],
    capabilities: list[AssignableCapabilityPermissionTarget],
) -> AssignablePermissionTargets:
    return AssignablePermissionTargets(
        connectors=tuple(sorted(connectors.values(), key=lambda item: item.connector_id)),
        capabilities=tuple(
            sorted(
                capabilities,
                key=lambda item: (item.connector_id, item.capability_kind, item.capability_key),
            )
        ),
    )


def _merge_connectors(
    result: dict[str, AssignableConnectorPermissionTarget],
    connectors: tuple[AssignableConnectorPermissionTarget, ...],
) -> None:
    for connector in connectors:
        existing = result.get(connector.connector_id)
        if existing is not None and existing != connector:
            raise ValueError("Duplicate connector permission identity")
        result[connector.connector_id] = connector


def _merge_capabilities(
    result: dict[tuple[str, str, str], AssignableCapabilityPermissionTarget],
    capabilities: tuple[AssignableCapabilityPermissionTarget, ...],
) -> None:
    for capability in capabilities:
        identity = (
            capability.connector_id,
            capability.capability_kind,
            capability.capability_key,
        )
        existing = result.get(identity)
        if existing is not None and existing != capability:
            raise ValueError("Duplicate capability permission identity")
        result[identity] = capability
