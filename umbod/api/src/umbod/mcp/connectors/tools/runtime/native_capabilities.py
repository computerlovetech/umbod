from collections.abc import Callable, Mapping, Sequence
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult

from umbod.core.capabilities import (
    CapabilityAvailability,
    CapabilityIdentity,
    NormalizedCapability,
)
from umbod.core.connectors.native.capabilities import NativeCapabilityCatalog
from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionKey,
    ConnectorCapabilityDescriptionOverrideStore,
    OverriddenCapabilityDescription,
)
from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.mcp.connectors.tools.definition.registrar import build_connector_tool_definition
from umbod.mcp.connectors.tools.discovery.search import ConnectorToolSearchCandidate
from umbod.mcp.connectors.tools.infrastructure.authorization import (
    ConnectorToolAuthorizationScope,
)
from umbod.mcp.connectors.tools.invocation.runner import ConnectorToolInvocationRunner


class NativeCapabilityRuntime:
    def __init__(
        self,
        catalog: NativeCapabilityCatalog,
        availability: CapabilityAvailability,
        invoker_factory: Callable[[ConnectorToolMapping], ConnectorToolInvocationRunner],
    ) -> None:
        self.catalog = catalog
        self._availability = availability
        self._invoker_factory = invoker_factory

    async def eligible_mappings(self, connector_id: str) -> list[ConnectorToolMapping]:
        mappings: list[ConnectorToolMapping] = []
        for capability in await self.catalog.list_capabilities():
            if capability.identity.connector_id != connector_id:
                continue
            binding = self.catalog.resolve_binding(capability.identity)
            if binding.mapping is not None and await self._availability.is_available(
                capability.identity
            ):
                mappings.append(binding.mapping)
        return mappings

    async def is_available(self, identity: CapabilityIdentity) -> bool:
        return await self._availability.is_available(identity)

    async def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        authorization_scope: ConnectorToolAuthorizationScope,
    ) -> ToolResult | None:
        binding = self.catalog.resolve_public_name(tool_name)
        if binding is None or binding.mapping is None:
            return None
        identity = binding.capability.identity
        tool_ref = ConnectorToolRef(identity.connector_id, identity.capability_key)
        if not authorization_scope.allows(tool_ref):
            return None
        if not await self._availability.is_available(identity):
            return None
        definition = build_connector_tool_definition(
            binding.mapping, self._invoker_factory(binding.mapping)
        )
        return await definition.run(dict(arguments))


class NativeCapabilitySearch:
    def __init__(
        self,
        runtime: NativeCapabilityRuntime,
        connector_display_names: Mapping[str, str],
        connector_descriptions: Mapping[str, str],
        description_overrides: ConnectorCapabilityDescriptionOverrideStore,
    ) -> None:
        self._runtime = runtime
        self._display_names = connector_display_names
        self._descriptions = connector_descriptions
        self._description_overrides = description_overrides

    async def candidates(
        self, authorization_scope: ConnectorToolAuthorizationScope
    ) -> list[ConnectorToolSearchCandidate]:
        capabilities = await self._authorized_capabilities(authorization_scope)
        descriptions = await self._effective_descriptions(capabilities)
        return [self._candidate(capability.identity, descriptions) for capability in capabilities]

    async def _authorized_capabilities(
        self, authorization_scope: ConnectorToolAuthorizationScope
    ) -> tuple[NormalizedCapability, ...]:
        eligible = []
        for capability in await self._runtime.catalog.list_capabilities():
            identity = capability.identity
            tool_ref = ConnectorToolRef(identity.connector_id, identity.capability_key)
            if authorization_scope.allows(tool_ref) and await self._runtime.is_available(identity):
                eligible.append(capability)
        return tuple(eligible)

    async def _effective_descriptions(
        self, capabilities: Sequence[NormalizedCapability]
    ) -> dict[str, str]:
        connector_ids = tuple(dict.fromkeys(item.identity.connector_id for item in capabilities))
        keys = tuple(
            ConnectorCapabilityDescriptionKey(kind="native", connector_id=connector_id)
            for connector_id in connector_ids
        )
        states = await self._description_overrides.get_many(keys)
        return {
            connector_id: state.description
            if isinstance(state, OverriddenCapabilityDescription)
            else self._descriptions[connector_id]
            for connector_id, state in zip(connector_ids, states, strict=True)
        }

    def _candidate(
        self, identity: CapabilityIdentity, descriptions: Mapping[str, str]
    ) -> ConnectorToolSearchCandidate:
        binding = self._runtime.catalog.resolve_binding(identity)
        capability = binding.capability
        return ConnectorToolSearchCandidate(
            tool_name=binding.public_tool_name,
            description=capability.description,
            connector_id=identity.connector_id,
            connector_display_name=self._display_names.get(identity.connector_id, identity.connector_id),
            connector_capability_description=descriptions[identity.connector_id],
            operation_name=identity.capability_key,
            input_schema=capability.input_schema,
        )


def ensure_unique_candidates(candidates: Sequence[ConnectorToolSearchCandidate]) -> None:
    candidate_names: set[str] = set()
    for candidate in candidates:
        if candidate.tool_name in candidate_names:
            raise ToolError(f"public_tool_name_conflict:{candidate.tool_name}")
        candidate_names.add(candidate.tool_name)
