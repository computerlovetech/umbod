from tests.support.native_tool_states import enabled_native_tool_states
from dataclasses import replace
from typing import cast

from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.signals.execution import SignalToolExecutionPipelineFactory
from umbod.mcp.metrics import PrometheusMcpMetricsRecorder
from umbod.mcp.logging import create_default_mcp_audit_recorder

from fastmcp import FastMCP
from fastmcp.server.middleware import AuthMiddleware
from pydantic import SecretStr

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, install_authorization
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool
from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import ExecutionCase, execution_case
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import InvocationLog, provider_for
from tests.umbod.mcp.test_personal_caller import _settings
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, PersonalConnectionKey, SetPersonalConnectionEnabled
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import authorize_personal_grant
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalToolInventory
from umbod.core.connectors.downstream_mcp.personal_tools.service import PersonalToolDiscoveryService
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalCallerProvider, McpPersonalToolRuntime, PersonalDiscoveryMiddleware, PersonalToolReservationMiddleware, personal_tool_permission_check
from umbod.mcp.connectors.native.tools import RuntimeConnectorToolRegistry, register_connector_tools
from umbod.mcp.logging import create_default_mcp_tool_invocation_log_sink


async def _install_bob(case: RuntimeCase) -> RuntimeCase:
    key = PersonalConnectionKey(principal=CanonicalPrincipal(namespace="trusted", subject="bob"), connector_id="personal")
    await case.bundle.personal_connections.set_enabled(SetPersonalConnectionEnabled(key=key, enabled=True))
    grant = case.grant.model_copy(update={"key": key, "access_token": SecretStr("bob-only-token")})
    bob = replace(case, query=case.query.model_copy(update={"key": key}), grant=grant)
    await install_authorization(bob, authorize_personal_grant(grant))
    return bob


async def _discover(execution: ExecutionCase, case: RuntimeCase, value_type: str) -> None:
    tool = approved_tool("read").model_copy(update={"description": f"Private {case.query.key.principal.subject} description", "input_schema": {"type": "object", "properties": {"value": {"type": value_type}}, "required": ["value"], "additionalProperties": False}})
    execution.transport.inventories[case.query.key] = PersonalToolInventory(tools=(tool,))
    await PersonalToolDiscoveryService(case.store, case.bundle.personal_tool_access, execution.transport, lambda: case.query.now).discover(case.query)


async def metadata_server(case: RuntimeCase, exposure: str) -> FastMCP:
    execution = await execution_case(case)
    await _discover(execution, case, "string")
    await _discover(execution, await _install_bob(case), "integer")
    settings = _settings(namespace="trusted")
    settings = settings.model_copy(update={"mcp": settings.mcp.model_copy(update={"permission_group_claim": "groups"})})
    runtime = McpPersonalToolRuntime(McpPersonalCallerProvider(settings), case.bundle.personal_tool_access, execution.transport, lambda: case.query.now)
    provider = await provider_for(replace(execution, runtime=runtime, contexts=McpPersonalCallerProvider(settings)), PermitAllConnectorInvocationPolicy(), InvocationLog())
    public = FastMCP("owner-metadata", middleware=[PersonalDiscoveryMiddleware(provider), AuthMiddleware(auth=personal_tool_permission_check(lambda context: True)), PersonalToolReservationMiddleware(provider)])
    public.downstream_mcp_tool_provider = provider
    if exposure == "flat":
        public.add_provider(provider)
        return public
    signals = create_mcp_signals(create_default_mcp_tool_invocation_log_sink(), PrometheusMcpMetricsRecorder(), create_default_mcp_audit_recorder("test"))
    await register_connector_tools(
        public,
        signals=signals,
        execution_pipelines=SignalToolExecutionPipelineFactory(signals, PermitAllConnectorInvocationPolicy()),
        connector_registrations=[],
        connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(),
        connector_publishing_store=case.bundle.publishing,
        connector_tool_mappings=[],
        connector_tool_runtime_state_store=enabled_native_tool_states(),
        connector_tool_exposure_mode=exposure,
    )
    cast(RuntimeConnectorToolRegistry, public.connector_tool_registry).add_gateway_provider(provider)
    return public
