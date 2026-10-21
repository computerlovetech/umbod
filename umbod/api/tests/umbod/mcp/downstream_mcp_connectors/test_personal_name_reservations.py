from typing import cast

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from tests.mcp_fixtures import build_test_mcp
from tests.persistence_runtime import create_inmemory_runtime
from tests.support.connector_plugins import SlackAdminConfiguration
from tests.umbod.core.downstream_mcp_connectors.personal_tools.runtime_support import execution_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.mcp.connectors.tools.test_connector_tool_gateway_runtime_acceptance import ConnectorToolMapping, _configuration
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import InvocationLog, provider_for
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE
from umbod.core.publishing.stores.service import ConnectorPublishingStoreService
from umbod.mcp.connectors.tools import InMemoryConnectorToolRuntimeStateStore, RuntimeConnectorToolRegistry
from umbod.mcp.connectors.tools.infrastructure.authorization import UnrestrictedConnectorTools
from umbod.mcp.downstream_mcp_connectors.personal_runtime import PersonalToolReservationMiddleware
from umbod.mcp.downstream_mcp_connectors.provider import reset_request_connector_scope, set_request_connector_scope
from umbod.mcp.settings import MCPAppSettings, MCPSettings

__all__ = ["runtime_case"]


@pytest.mark.asyncio
@pytest.mark.parametrize("withdrawal", ("identity", "disconnect", "publication"))
async def test_gateway_rejects_native_collision_before_execution(runtime_case: RuntimeCase, withdrawal: str) -> None:
    execution = await execution_case(runtime_case)
    if withdrawal == "identity":
        execution.contexts.contexts.clear()
    elif withdrawal == "disconnect":
        await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    else:
        await runtime_case.bundle.publishing.unpublish_connector("personal")
    provider = provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    configurations = InMemoryConnectorCurrentConfigurationStore()
    await configurations.save_current_configuration("Personal", _configuration())
    publications = ConnectorPublishingStoreService(create_inmemory_runtime().database, PUBLICATION_STATE_TABLE)
    await publications.publish_connector("Personal")
    activations = InMemoryConnectorToolRuntimeStateStore()
    activations.save_runtime_state(ConnectorToolRuntimeState(key=ConnectorToolRef("Personal", "read"), status="enabled"))
    alternate_calls: list[str] = []

    def alternate_native_source(value: str) -> dict[str, str]:
        alternate_calls.append(value)
        return {"owner": "shared"}

    public = await build_test_mcp(MCPAppSettings(mcp=MCPSettings(connector_tool_exposure_mode="gateway", _env_file=None), _env_file=None), None, connector_registrations=[{"id": "Personal", "display_name": "Alternate", "capability_description": "Alternate", "description": "Alternate", "configuration_schema": SlackAdminConfiguration}], connector_configuration_store=configurations, connector_publishing_store=publications, connector_tool_mappings=[ConnectorToolMapping("Personal", "read", "Alternate", alternate_native_source)], connector_tool_runtime_state_store=activations)
    registry = cast(RuntimeConnectorToolRegistry, public.connector_tool_registry)
    registry.add_gateway_provider(provider)
    assert await provider.owns_tool("Personal_read")
    with pytest.raises(ToolError, match="Tool is not available"):
        await registry.execute_tool("Personal_read", {"value": "same"}, UnrestrictedConnectorTools())
    with pytest.raises(ToolError, match="Tool is not available"):
        await registry.eligible_search_candidates(UnrestrictedConnectorTools())
    assert alternate_calls == []
    assert execution.transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("withdrawal", ("available", "identity", "disconnect", "publication"))
async def test_flat_reserved_name_never_executes_or_lists_alternate_component(runtime_case: RuntimeCase, withdrawal: str) -> None:
    execution = await execution_case(runtime_case)
    if withdrawal == "identity":
        execution.contexts.contexts.clear()
    elif withdrawal == "disconnect":
        await runtime_case.bundle.personal_connections.disconnect(runtime_case.query.key)
    elif withdrawal == "publication":
        await runtime_case.bundle.publishing.unpublish_connector("personal")
    provider = provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    public = FastMCP("reserved", providers=[provider], middleware=[PersonalToolReservationMiddleware(provider)])
    alternate_calls: list[str] = []

    @public.tool(name="Personal_read", meta={"connector_id": "personal", "operation_name": "read"})
    def alternate(value: str) -> dict[str, str]:
        alternate_calls.append(value)
        return {"owner": "shared"}

    async with Client(public) as client:
        assert "Personal_read" not in {tool.name for tool in await client.list_tools()}
        result = await client.call_tool("Personal_read", {"value": "same"}, raise_on_error=False)
    assert result.is_error
    assert alternate_calls == []
    assert execution.transport.calls == []


@pytest.mark.asyncio
async def test_personal_claims_follow_connector_scope_without_owner_context(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    execution.contexts.contexts.clear()
    provider = provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    assert await provider.personal_tool_name_claims() == ("Personal_read",)
    for scope, expected in (("other", ()), ("personal", ("read",))):
        token = set_request_connector_scope(scope)
        try:
            assert await provider.personal_tool_name_claims() == expected
        finally:
            reset_request_connector_scope(token)


@pytest.mark.asyncio
async def test_reservation_middleware_preserves_authorized_personal_and_unrelated_shared(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    provider = provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    public = FastMCP("reserved", providers=[provider], middleware=[PersonalToolReservationMiddleware(provider)])

    @public.tool(name="Shared_read")
    def shared() -> str:
        return "shared"

    async with Client(public) as client:
        assert {"Personal_read", "Shared_read"} <= {tool.name for tool in await client.list_tools()}
        assert (await client.call_tool("Personal_read", {"value": "same"})).structured_content == {"owner": "owner"}
        assert not (await client.call_tool("Shared_read", {})).is_error
    assert len(execution.transport.calls) == 1
