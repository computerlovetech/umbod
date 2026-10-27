from asyncio import Lock
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
from umbod.mcp.connectors.native.tools.definition.registrar import build_connector_tool_definition
from umbod.mcp.connectors.native.tools.discovery.search import ConnectorToolSearchCandidate
from umbod.mcp.connectors.native.tools.infrastructure.authorization import (
    ConnectorToolAuthorizationScope,
)
from umbod.mcp.connectors.native.tools.invocation.runner import ConnectorToolInvocationRunner
from umbod.mcp.connectors.native.tools.invocation.ports import NativeToolExecutionAdmission


class NativeCapabilityRuntime:
    def __init__(
        self,
        catalog: NativeCapabilityCatalog,
        availability: CapabilityAvailability,
        invoker_factory: Callable[[ConnectorToolMapping], ConnectorToolInvocationRunner],
        execution_admission: NativeToolExecutionAdmission,
    ) -> None:
        self.catalog = catalog
        self._availability = availability
        self._invoker_factory = invoker_factory
        self._execution_admission = execution_admission

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

    async def admit_execution(self, identity: CapabilityIdentity) -> None:
        await self._execution_admission(identity)

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
        self._candidates: tuple[ConnectorToolSearchCandidate, ...] = ()
        self._refresh_lock = Lock()

    def invalidate(self) -> None:
        self._candidates = ()

    async def refresh(self) -> None:
        async with self._refresh_lock:
            await self._refresh()

    async def _refresh(self) -> None:
        try:
            capabilities = tuple([
                capability
                for capability in await self._runtime.catalog.list_capabilities()
                if await self._runtime.is_available(capability.identity)
            ])
            descriptions = await self._effective_descriptions(capabilities)
            candidates = tuple(
                self._candidate(capability.identity, descriptions) for capability in capabilities
            )
        except Exception:
            self._candidates = ()
            raise
        self._candidates = candidates

    async def candidates(
        self, authorization_scope: ConnectorToolAuthorizationScope
    ) -> list[ConnectorToolSearchCandidate]:
        snapshot = self._candidates
        return [
            candidate.model_copy(deep=True) for candidate in snapshot
            if authorization_scope.allows(
                ConnectorToolRef(candidate.connector_id, candidate.operation_name)
            )
        ]

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
