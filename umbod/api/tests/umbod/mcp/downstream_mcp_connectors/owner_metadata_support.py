from dataclasses import replace
from typing import cast

from fastmcp import FastMCP
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
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalCallerProvider, McpPersonalToolRuntime, PersonalToolReservationMiddleware
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
    runtime = McpPersonalToolRuntime(McpPersonalCallerProvider(settings), case.bundle.definitions, case.bundle.personal_tool_access, execution.transport, lambda: case.query.now)
    provider = provider_for(replace(execution, runtime=runtime), PermitAllConnectorInvocationPolicy(), InvocationLog())
    public = FastMCP("owner-metadata", middleware=[PersonalToolReservationMiddleware(provider)])
    if exposure == "flat":
        public.add_provider(provider)
        return public
    await register_connector_tools(public, invocation_policy=PermitAllConnectorInvocationPolicy(), connector_registrations=[], connector_configuration_store=InMemoryConnectorCurrentConfigurationStore(), connector_publishing_store=case.bundle.publishing, connector_tool_mappings=[], connector_tool_exposure_mode=exposure, tool_invocation_log_sink=create_default_mcp_tool_invocation_log_sink())
    cast(RuntimeConnectorToolRegistry, public.connector_tool_registry).add_gateway_provider(provider)
    return public
