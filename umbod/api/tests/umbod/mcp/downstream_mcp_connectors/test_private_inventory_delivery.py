import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool, replace_policy
from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import execution_case
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import InvocationLog, provider_for
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.connectors.downstream_mcp.models import ToolCatalogSnapshot
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalToolInventory, PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_tools.service import PersonalToolDiscoveryService
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, ReplaceToolCatalog, SaveConnectorDefinition
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.core.permissions.stores.schema import CAPABILITY_PERMISSION_TABLE
from umbod.core.persistence import DeleteQuery, NoFilter, TransactionMode
from umbod.mcp.connectors.downstream_mcp.personal_runtime import PersonalToolReservationMiddleware
from umbod.mcp.connectors.downstream_mcp.provider import reset_request_connector_scope, set_request_connector_scope

__all__ = ["runtime_case"]


@pytest.mark.asyncio
async def test_private_new_tools_require_rediscovery_but_not_global_configuration(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    held = await provider.get_tool("Personal_read")
    new_tool = approved_tool("new_private")
    execution.transport.inventories[runtime_case.query.key] = PersonalToolInventory(tools=(approved_tool("read"), new_tool))
    execution.transport.results[(runtime_case.query.key, "new_private")] = PersonalToolResult(result={"content": [], "structuredContent": {"owner": "owner"}})
    assert [tool.name for tool in await provider.list_tools()] == ["Personal_read"]
    with pytest.raises(ToolError, match="not available"):
        await provider.execute_tool("Personal_new_private", {"value": "same"})
    await PersonalToolDiscoveryService(runtime_case.store, runtime_case.bundle.personal_tool_access, execution.transport, lambda: runtime_case.query.now).discover(runtime_case.query)
    assert await provider.configured_tool_name_claims() == ()
    assert (await runtime_case.bundle.catalogs.get(ConnectorIdQuery(connector_id="personal"))).found is False
    public = FastMCP("private-inventory", providers=[provider], middleware=[PersonalToolReservationMiddleware(provider)])
    async with Client(public) as client:
        assert {tool.name for tool in await client.list_tools()} == {"Personal_read", "Personal_new_private"}
        assert not (await client.call_tool("Personal_new_private", {"value": "same"})).is_error
    assert {candidate.tool_name for candidate in await provider.eligible_search_candidates()} == {"Personal_read", "Personal_new_private"}
    assert (await held.run({"value": "same"})).is_error


@pytest.mark.asyncio
async def test_legacy_policy_activation_and_tool_grants_do_not_control_private_inventory(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    held = await provider.get_tool("Personal_read")
    await replace_policy(runtime_case, (approved_tool("legacy_only"),))
    await runtime_case.bundle.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(connector_id="personal", discovered_at=runtime_case.query.now, tools=(approved_tool("legacy-name"), approved_tool("legacy_name")))))
    await runtime_case.bundle.activations.set_status(CapabilityRef(connector_kind="downstream_mcp", connector_id="personal", capability_kind="tool", capability_key="read"), ActivationStatus.DISABLED)
    async with runtime_case.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.delete(CAPABILITY_PERMISSION_TABLE, DeleteQuery(NoFilter()))
    assert [tool.name for tool in await provider.list_tools()] == ["Personal_read"]
    assert [candidate.tool_name for candidate in await provider.eligible_search_candidates()] == ["Personal_read"]
    assert not (await held.run({"value": "same"})).is_error


@pytest.mark.asyncio
@pytest.mark.parametrize(("prefix", "reserved", "unrelated"), (("Personal-tools", "Personal_tools_new", "Personal_read"), ("__Personal", "Personal_new", "Other_new"), ("Personal-", "Personal__new", "Personal_new")))
async def test_namespace_reservation_uses_mangled_definition_prefix(runtime_case: RuntimeCase, prefix: str, reserved: str, unrelated: str) -> None:
    execution = await execution_case(runtime_case)
    definition = (await runtime_case.bundle.definitions.get(ConnectorIdQuery(connector_id="personal"))).definition
    await runtime_case.bundle.definitions.save(SaveConnectorDefinition(definition=definition.model_copy(update={"tool_name_prefix": prefix})))
    execution.contexts.contexts.clear()
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    assert await provider.is_personal_tool_name(reserved)
    assert await provider.is_personal_tool_name(reserved.removesuffix("new").rstrip("_"))
    assert await provider.owns_tool(reserved)
    assert not await provider.is_personal_tool_name(unrelated)


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ("--", "___"))
async def test_degenerate_personal_namespace_fails_closed_instead_of_claiming_all_names(runtime_case: RuntimeCase, prefix: str) -> None:
    execution = await execution_case(runtime_case)
    definition = (await runtime_case.bundle.definitions.get(ConnectorIdQuery(connector_id="personal"))).definition
    await runtime_case.bundle.definitions.save(SaveConnectorDefinition(definition=definition.model_copy(update={"tool_name_prefix": prefix})))
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    for name in ("read", "Shared_read"):
        with pytest.raises(ToolError, match="public_tool_name_conflict"):
            await provider.is_personal_tool_name(name)
    with pytest.raises(ToolError, match="public_tool_name_conflict"):
        await provider.list_tools()
    token = set_request_connector_scope("personal")
    try:
        with pytest.raises(ToolError, match="public_tool_name_conflict"):
            await provider.is_personal_tool_name("read")
    finally:
        reset_request_connector_scope(token)
