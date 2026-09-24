from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from umbod.proxies import Model

from umbod.core.configuration import ConnectorCurrentConfigurationStore
from umbod.core.invocation import ConnectorInvocationPolicy
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
from umbod.core.invocation.tools.execution import create_tool_execution_pipeline
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.mcp.connectors.tools.infrastructure.authorization import (
    ConnectorToolAuthorizationScope,
)

from umbod.mcp.connectors.tools.infrastructure.client_notifications import (
    ToolListChangedClientNotifier,
)
from umbod.mcp.connectors.tools.runtime.ports import ConnectorToolExposureStrategy
from umbod.mcp.connectors.tools.invocation.runner import ConnectorToolInvocationRunner
from umbod.mcp.connectors.tools.invocation.telemetry import (
    ConnectorTelemetryInterceptor,
)
from umbod.mcp.connectors.tools.invocation.errors import ConnectorToolErrorFormatter
from umbod.mcp.connectors.tools.definition.naming import _mangle_tool_name
from umbod.mcp.connectors.tools.runtime.ports import RuntimeReconciliationResult
from umbod.mcp.connectors.tools.discovery.search import ConnectorToolSearchCandidate
from umbod.mcp.connectors.tools.runtime.native_capabilities import (
    NativeCapabilityRuntime,
    NativeCapabilitySearch,
    ensure_unique_candidates,
)
from umbod.mcp.metrics import McpMetricsRecorder
from umbod.mcp.logging import (
    McpAuditRecorder,
    McpToolInvocationLogSink,
    create_default_connector_tool_invocation_logger,
)


class ConnectorToolGatewayProvider(Protocol):
    async def eligible_search_candidates(self) -> list[ConnectorToolSearchCandidate]: ...

    def owns_tool(self, tool_name: str) -> bool: ...

    async def execute_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> ToolResult: ...


def _raise_for_unknown_optional_dependencies(optional_dependencies: Mapping[str, object]) -> None:
    unknown_dependency_names = set(optional_dependencies) - {
        "audit_recorder",
        "client_notifier",
        "connector_tool_runtime_state_store",
        "exposure_strategy",
        "metrics_recorder",
        "invocation_policy",
    }
    if unknown_dependency_names:
        unknown_dependency_name = next(iter(unknown_dependency_names))
        raise TypeError(
            f"RuntimeConnectorToolRegistry() got an unexpected keyword argument '{unknown_dependency_name}'"
        )


def _client_notifier_from_optional_dependencies(
    optional_dependencies: Mapping[str, object],
) -> ToolListChangedClientNotifier | None:
    return cast(ToolListChangedClientNotifier | None, optional_dependencies.get("client_notifier"))


def _runtime_state_store_from_optional_dependencies(
    optional_dependencies: Mapping[str, object],
) -> ConnectorToolRuntimeStateReader | None:
    return cast(
        ConnectorToolRuntimeStateReader | None,
        optional_dependencies.get("connector_tool_runtime_state_store"),
    )


def _audit_recorder_from_optional_dependencies(
    optional_dependencies: Mapping[str, object],
) -> McpAuditRecorder:
    audit_recorder = optional_dependencies.get("audit_recorder")
    if audit_recorder is None:
        raise TypeError(
            "RuntimeConnectorToolRegistry() missing required keyword-only argument: 'audit_recorder'"
        )
    return cast(McpAuditRecorder, audit_recorder)


def _exposure_strategy_from_optional_dependencies(
    optional_dependencies: Mapping[str, object],
) -> ConnectorToolExposureStrategy:
    exposure_strategy = optional_dependencies.get("exposure_strategy")
    if exposure_strategy is None:
        raise TypeError(
            "RuntimeConnectorToolRegistry() missing required keyword-only argument: 'exposure_strategy'"
        )
    return cast(ConnectorToolExposureStrategy, exposure_strategy)


@dataclass(frozen=True)
class ConnectorToolInvokerDependencies:
    error_formatter: ConnectorToolErrorFormatter
    tool_invocation_log_sink: McpToolInvocationLogSink
    audit_recorder: McpAuditRecorder
    metrics_recorder: McpMetricsRecorder
    connector_display_names: Mapping[str, str]
    invocation_policy: ConnectorInvocationPolicy


def create_connector_tool_invoker_factory(
    dependencies: ConnectorToolInvokerDependencies,
) -> Callable[[ConnectorToolMapping], ConnectorToolInvocationRunner]:
    def invoker_for_mapping(mapping: ConnectorToolMapping) -> ConnectorToolInvocationRunner:
        telemetry_interceptor = ConnectorTelemetryInterceptor(
            connector_name=dependencies.connector_display_names.get(
                mapping.connector_id, mapping.connector_id
            ),
            tool_invocation_logger=create_default_connector_tool_invocation_logger(
                dependencies.tool_invocation_log_sink,
                dependencies.audit_recorder,
            ),
            metrics_recorder=dependencies.metrics_recorder,
            result_is_error=lambda result: False,
        )
        return ConnectorToolInvocationRunner(
            mapping=mapping,
            error_formatter=dependencies.error_formatter,
            execution_pipeline=create_tool_execution_pipeline(
                dependencies.invocation_policy,
                (telemetry_interceptor,),
            ),
        )

    return invoker_for_mapping


def _server_name(mcp: FastMCP) -> str:
    name = getattr(mcp, "name", None)
    if isinstance(name, str):
        return name
    return "umbod"


@dataclass(frozen=True)
class _NativeRuntimeConfiguration:
    schemas: Mapping[str, type[Model]]
    configuration_store: ConnectorCurrentConfigurationStore
    publishing_store: ConnectorPublishingStore
    mappings: Sequence[ConnectorToolMapping]
    display_names: Mapping[str, str]
    error_formatter: ConnectorToolErrorFormatter
    log_sink: McpToolInvocationLogSink
    optional_dependencies: Mapping[str, object]
    capability_descriptions: Mapping[str, str]
    description_overrides: ConnectorCapabilityDescriptionOverrideStore


@dataclass
class _RegistryState:
    schemas: Mapping[str, type[Model]]
    client_notifier: ToolListChangedClientNotifier | None
    exposure_strategy: ConnectorToolExposureStrategy
    gateway_providers: list[ConnectorToolGatewayProvider]
    native: NativeCapabilityRuntime
    search: NativeCapabilitySearch


def _create_native_runtime(
    configuration: _NativeRuntimeConfiguration,
) -> NativeCapabilityRuntime:
    dependencies = configuration.optional_dependencies
    availability = CapabilityAvailability(
        ConnectorStoreCapabilityPublication("native", configuration.publishing_store),
        NativeCapabilityActivation(_runtime_state_store_from_optional_dependencies(dependencies)),
        NativeCapabilityReadiness(configuration.schemas, configuration.configuration_store),
        UnrestrictedCapabilityPermissionPolicy(),
    )
    invoker_factory = create_connector_tool_invoker_factory(
        ConnectorToolInvokerDependencies(
            error_formatter=configuration.error_formatter,
            tool_invocation_log_sink=configuration.log_sink,
            audit_recorder=_audit_recorder_from_optional_dependencies(dependencies),
            metrics_recorder=cast(McpMetricsRecorder, dependencies["metrics_recorder"]),
            connector_display_names=configuration.display_names,
            invocation_policy=cast(ConnectorInvocationPolicy, dependencies["invocation_policy"]),
        )
    )
    return NativeCapabilityRuntime(
        NativeCapabilityCatalog.from_mappings(configuration.mappings),
        availability,
        invoker_factory,
    )


def _create_registry_state(configuration: _NativeRuntimeConfiguration) -> _RegistryState:
    dependencies = configuration.optional_dependencies
    native = _create_native_runtime(configuration)
    return _RegistryState(
        configuration.schemas,
        _client_notifier_from_optional_dependencies(dependencies),
        _exposure_strategy_from_optional_dependencies(dependencies),
        [],
        native,
        NativeCapabilitySearch(
            native, configuration.display_names, configuration.capability_descriptions,
            configuration.description_overrides,
        ),
    )


class _RegistryReconciliation:
    _state: _RegistryState

    async def reconcile_all(self) -> None:
        for connector_id in self._state.native.catalog.connector_ids():
            await self.reconcile_connector(connector_id)

    async def reconcile_connector(self, connector_id: str) -> None:
        mappings = await self._state.native.eligible_mappings(connector_id)
        self._state.exposure_strategy.reconcile_connector(connector_id, mappings)

    async def handle_publish_state_changed(self, event: ConnectorPublishStateChanged) -> None:
        await self.reconcile_connector(event.connector_id)

    async def reconcile_runtime_state(self, key: ConnectorToolRef) -> RuntimeReconciliationResult:
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
        return self._state.exposure_strategy.reconcile_runtime_state(
            key.connector_id, tool_name, mappings
        )


class _RegistryGateway:
    _state: _RegistryState

    def add_gateway_provider(self, provider: ConnectorToolGatewayProvider) -> None:
        self._state.gateway_providers.append(provider)

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        authorization_scope: ConnectorToolAuthorizationScope,
    ) -> ToolResult:
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
        for provider in self._state.gateway_providers:
            candidates.extend(await provider.eligible_search_candidates())
        ensure_unique_candidates(candidates)
        return candidates


class _RegistryMetadata:
    _state: _RegistryState

    @property
    def client_notifier(self) -> ToolListChangedClientNotifier | None:
        return self._state.client_notifier

    def configuration_schema_for_connector(self, connector_id: str) -> type[Model] | None:
        return self._state.schemas.get(connector_id)


class RuntimeConnectorToolRegistry(
    _RegistryReconciliation, _RegistryGateway, _RegistryMetadata
):
    def __init__(self, mcp: FastMCP, *,
        schemas: Mapping[str, type[Model]],
        connector_display_names: Mapping[str, str],
        connector_capability_descriptions: Mapping[str, str],
        connector_configuration_store: ConnectorCurrentConfigurationStore,
        connector_publishing_store: ConnectorPublishingStore,
        connector_tool_mappings: Sequence[ConnectorToolMapping],
        capability_description_overrides: ConnectorCapabilityDescriptionOverrideStore,
        error_formatter: ConnectorToolErrorFormatter,
        tool_invocation_log_sink: McpToolInvocationLogSink,
        **optional_dependencies: object,
    ) -> None:
        _raise_for_unknown_optional_dependencies(optional_dependencies)
        configuration = _NativeRuntimeConfiguration(
            schemas, connector_configuration_store, connector_publishing_store,
            connector_tool_mappings, connector_display_names, error_formatter,
            tool_invocation_log_sink, optional_dependencies,
            connector_capability_descriptions, capability_description_overrides,
        )
        self._state = _create_registry_state(configuration)
        self._connector_configuration_store = connector_configuration_store
        self._connector_publishing_store = connector_publishing_store
