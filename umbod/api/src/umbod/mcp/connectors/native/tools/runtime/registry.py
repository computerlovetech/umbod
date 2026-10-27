from asyncio import Lock
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from umbod.proxies import Model

from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.invocation import ConnectorInvocationDenied
from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionOverrideStore,
)
from umbod.core.publishing import (
    ConnectorPublishStateChanged,
    ConnectorPublishingStore,
)
from umbod.core.capabilities import (
    CapabilityAvailability,
    CapabilityIdentity,
    ConnectorStoreCapabilityPublication,
    UnrestrictedCapabilityPermissionPolicy,
)
from umbod.core.connectors.native.capabilities import (
    ConnectorToolRuntimeStateReader,
    NativeCapabilityActivation,
    NativeCapabilityCatalog,
    NativeCapabilityReadiness,
)
from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.mcp.connectors.native.tools.infrastructure.authorization import (
    ConnectorToolAuthorizationScope,
)

from umbod.mcp.connectors.native.tools.infrastructure.client_notifications import (
    ToolListChangedClientNotifier,
)
from umbod.mcp.connectors.native.tools.runtime.ports import ConnectorToolExposureStrategy
from umbod.mcp.connectors.native.tools.invocation.runner import ConnectorToolInvocationRunner
from umbod.mcp.connectors.native.tools.invocation.ports import NativeToolExecutionAdmission
from umbod.mcp.connectors.native.tools.invocation.errors import ConnectorToolErrorFormatter
from umbod.mcp.connectors.native.tools.definition.naming import _mangle_tool_name
from umbod.mcp.connectors.native.tools.runtime.ports import RuntimeReconciliationResult
from umbod.mcp.connectors.native.tools.discovery.search import ConnectorToolSearchCandidate
from umbod.mcp.connectors.native.tools.runtime.native_capabilities import (
    NativeCapabilityRuntime,
    NativeCapabilitySearch,
    ensure_unique_candidates,
)
from umbod.mcp.signals.execution import McpToolExecutionPipelineFactory


@runtime_checkable
class PersonalToolNamespace(Protocol):
    async def is_personal_tool_name(self, name: str) -> bool: ...


class ConnectorToolGatewayProvider(Protocol):
    async def eligible_search_candidates(self) -> list[ConnectorToolSearchCandidate]: ...

    async def configured_tool_name_claims(self) -> tuple[str, ...]: ...

    async def owns_tool(self, tool_name: str) -> bool: ...

    async def execute_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> ToolResult: ...


@dataclass(frozen=True)
class ConnectorToolInvokerDependencies:
    error_formatter: ConnectorToolErrorFormatter
    execution_pipelines: McpToolExecutionPipelineFactory
    connector_display_names: Mapping[str, str]
    execution_admission: NativeToolExecutionAdmission


def create_connector_tool_invoker_factory(
    dependencies: ConnectorToolInvokerDependencies,
) -> Callable[[ConnectorToolMapping], ConnectorToolInvocationRunner]:
    def invoker_for_mapping(mapping: ConnectorToolMapping) -> ConnectorToolInvocationRunner:
        return ConnectorToolInvocationRunner(
            mapping=mapping,
            error_formatter=dependencies.error_formatter,
            execution_admission=dependencies.execution_admission,
            execution_pipeline=dependencies.execution_pipelines.create(
                dependencies.connector_display_names.get(mapping.connector_id, mapping.connector_id),
                result_is_error=lambda result: False,
            ),
        )

    return invoker_for_mapping


@dataclass(frozen=True)
class _NativeRuntimeConfiguration:
    schemas: Mapping[str, type[Model]]
    configuration_store: ConnectorCurrentConfigurationStore
    publishing_store: ConnectorPublishingStore
    mappings: Sequence[ConnectorToolMapping]
    display_names: Mapping[str, str]
    error_formatter: ConnectorToolErrorFormatter
    execution_pipelines: McpToolExecutionPipelineFactory
    client_notifier: ToolListChangedClientNotifier
    runtime_state_store: ConnectorToolRuntimeStateReader
    exposure_strategy: ConnectorToolExposureStrategy
    capability_descriptions: Mapping[str, str]
    description_overrides: ConnectorCapabilityDescriptionOverrideStore
    execution_authorization_scope: Callable[[], ConnectorToolAuthorizationScope]


@dataclass
class _RegistryState:
    schemas: Mapping[str, type[Model]]
    client_notifier: ToolListChangedClientNotifier
    exposure_strategy: ConnectorToolExposureStrategy
    gateway_providers: list[ConnectorToolGatewayProvider]
    native: NativeCapabilityRuntime
    search: NativeCapabilitySearch
    reconciliation_lock: Lock
    exposure_invalidated: bool


def _create_native_runtime(
    configuration: _NativeRuntimeConfiguration,
) -> NativeCapabilityRuntime:
    availability = CapabilityAvailability(
        ConnectorStoreCapabilityPublication("native", configuration.publishing_store),
        NativeCapabilityActivation(configuration.runtime_state_store),
        NativeCapabilityReadiness(configuration.schemas, configuration.configuration_store),
        UnrestrictedCapabilityPermissionPolicy(),
    )

    async def admit_execution(identity: CapabilityIdentity) -> None:
        try:
            scope = configuration.execution_authorization_scope()
            tool_ref = ConnectorToolRef(identity.connector_id, identity.capability_key)
            if scope.allows(tool_ref) and await availability.is_available(identity):
                return
        except Exception:
            raise ConnectorInvocationDenied("Connector invocation denied") from None
        raise ConnectorInvocationDenied("Connector invocation denied")

    invoker_factory = create_connector_tool_invoker_factory(
        ConnectorToolInvokerDependencies(
            error_formatter=configuration.error_formatter,
            execution_pipelines=configuration.execution_pipelines,
            connector_display_names=configuration.display_names,
            execution_admission=admit_execution,
        )
    )
    return NativeCapabilityRuntime(
        NativeCapabilityCatalog.from_mappings(configuration.mappings),
        availability,
        invoker_factory,
        admit_execution,
    )


def _create_registry_state(configuration: _NativeRuntimeConfiguration) -> _RegistryState:
    native = _create_native_runtime(configuration)
    return _RegistryState(
        configuration.schemas,
        configuration.client_notifier,
        configuration.exposure_strategy,
        [],
        native,
        NativeCapabilitySearch(
            native, configuration.display_names, configuration.capability_descriptions,
            configuration.description_overrides,
        ),
        Lock(),
        False,
    )


class _RegistryReconciliation:
    _state: _RegistryState

    @asynccontextmanager
    async def _reconciliation(self, recover_exposure: bool) -> AsyncIterator[None]:
        async with self._state.reconciliation_lock:
            try:
                if recover_exposure and self._state.exposure_invalidated:
                    await self._reconcile_all()
                yield
            except Exception:
                self._state.exposure_invalidated = True
                self._state.search.invalidate()
                for connector_id in self._state.native.catalog.connector_ids():
                    self._state.exposure_strategy.reconcile_connector(connector_id, ())
                raise

    async def refresh_discovery(self) -> None:
        await self.reconcile_all()

    async def reconcile_all(self) -> None:
        async with self._reconciliation(recover_exposure=False):
            await self._reconcile_all()

    async def _reconcile_all(self) -> None:
        projections = [
            (connector_id, await self._state.native.eligible_mappings(connector_id))
            for connector_id in self._state.native.catalog.connector_ids()
        ]
        await self._state.search.refresh()
        for connector_id, mappings in projections:
            self._state.exposure_strategy.reconcile_connector(connector_id, mappings)
        self._state.exposure_invalidated = False

    async def reconcile_connector(self, connector_id: str) -> None:
        async with self._reconciliation(recover_exposure=True):
            mappings = await self._state.native.eligible_mappings(connector_id)
            await self._state.search.refresh()
            self._state.exposure_strategy.reconcile_connector(connector_id, mappings)

    async def handle_publish_state_changed(self, event: ConnectorPublishStateChanged) -> None:
        await self.reconcile_connector(event.connector_id)

    async def reconcile_runtime_state(self, key: ConnectorToolRef) -> RuntimeReconciliationResult:
        async with self._reconciliation(recover_exposure=True):
            return await self._reconcile_runtime_state(key)

    async def _reconcile_runtime_state(self, key: ConnectorToolRef) -> RuntimeReconciliationResult:
        identity = CapabilityIdentity(
            connector_kind="native",
            connector_id=key.connector_id,
            capability_kind="tool",
            capability_key=key.operation_name,
        )
        try:
            tool_name = self._state.native.catalog.resolve_binding(identity).public_tool_name
        except LookupError:
            tool_name = _mangle_tool_name(key.connector_id, key.operation_name)
        mappings = await self._state.native.eligible_mappings(key.connector_id)
        await self._state.search.refresh()
        return self._state.exposure_strategy.reconcile_runtime_state(
            key.connector_id, tool_name, mappings
        )


class _RegistryGateway:
    _state: _RegistryState

    async def admit_execution(self, identity: CapabilityIdentity) -> None:
        await self._state.native.admit_execution(identity)

    def add_gateway_provider(self, provider: ConnectorToolGatewayProvider) -> None:
        self._state.gateway_providers.append(provider)

    async def _validate_configured_name_claims(self) -> None:
        names: set[str] = set()
        for capability in await self._state.native.catalog.list_capabilities():
            if capability.identity.capability_kind != "tool":
                continue
            name = self._state.native.catalog.resolve_binding(capability.identity).public_tool_name
            if name in names:
                raise ToolError("Tool is not available")
            names.add(name)
        checked_providers: list[ConnectorToolGatewayProvider] = []
        for provider in self._state.gateway_providers:
            if isinstance(provider, PersonalToolNamespace):
                for name in names:
                    if await provider.is_personal_tool_name(name):
                        raise ToolError("Tool is not available")
            for name in await provider.configured_tool_name_claims():
                if name in names:
                    raise ToolError("Tool is not available")
                for previous in checked_providers:
                    if isinstance(previous, PersonalToolNamespace) and await previous.is_personal_tool_name(name):
                        raise ToolError("Tool is not available")
                names.add(name)
            checked_providers.append(provider)

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        authorization_scope: ConnectorToolAuthorizationScope,
    ) -> ToolResult:
        await self.eligible_search_candidates(authorization_scope)
        result = await self._state.native.execute(tool_name, arguments, authorization_scope)
        if result is not None:
            return result
        for provider in self._state.gateway_providers:
            if await provider.owns_tool(tool_name):
                return await provider.execute_tool(tool_name, arguments)
        raise ToolError(f"Unknown tool: '{tool_name}'")

    async def eligible_search_candidates(
        self,
        authorization_scope: ConnectorToolAuthorizationScope,
    ) -> list[ConnectorToolSearchCandidate]:
        candidates = await self._state.search.candidates(authorization_scope)
        await self._validate_configured_name_claims()
        for provider in self._state.gateway_providers:
            candidates.extend(await provider.eligible_search_candidates())
        ensure_unique_candidates(candidates)
        return candidates


class _RegistryMetadata:
    _state: _RegistryState

    @property
    def client_notifier(self) -> ToolListChangedClientNotifier:
        return self._state.client_notifier

    def configuration_schema_for_connector(self, connector_id: str) -> type[Model] | None:
        return self._state.schemas.get(connector_id)


class RuntimeConnectorToolRegistry(
    _RegistryReconciliation, _RegistryGateway, _RegistryMetadata
):
    def __init__(self, *,
        schemas: Mapping[str, type[Model]],
        connector_display_names: Mapping[str, str],
        connector_capability_descriptions: Mapping[str, str],
        connector_configuration_store: ConnectorCurrentConfigurationStore,
        connector_publishing_store: ConnectorPublishingStore,
        connector_tool_mappings: Sequence[ConnectorToolMapping],
        capability_description_overrides: ConnectorCapabilityDescriptionOverrideStore,
        error_formatter: ConnectorToolErrorFormatter,
        execution_pipelines: McpToolExecutionPipelineFactory,
        execution_authorization_scope: Callable[[], ConnectorToolAuthorizationScope],
        client_notifier: ToolListChangedClientNotifier,
        connector_tool_runtime_state_store: ConnectorToolRuntimeStateReader,
        exposure_strategy: ConnectorToolExposureStrategy,
    ) -> None:
        configuration = _NativeRuntimeConfiguration(
            schemas, connector_configuration_store, connector_publishing_store,
            connector_tool_mappings, connector_display_names, error_formatter,
            execution_pipelines, client_notifier, connector_tool_runtime_state_store,
            exposure_strategy,
            connector_capability_descriptions, capability_description_overrides,
            execution_authorization_scope,
        )
        self._state = _create_registry_state(configuration)
