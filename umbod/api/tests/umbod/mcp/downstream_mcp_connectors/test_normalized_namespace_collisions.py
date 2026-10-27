import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import execution_case
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_dispatch_collision import install_shared_alias
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import InvocationLog, provider_for
from umbod.core.capabilities.tools.names import mangle_public_tool_name
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, SaveConnectorDefinition
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.mcp.connectors.downstream_mcp.personal_runtime import PersonalToolReservationMiddleware

__all__ = ["runtime_case"]


async def _prefix(case: RuntimeCase, connector: str, prefix: str) -> None:
    definition = (await case.bundle.definitions.get(ConnectorIdQuery(connector_id=connector))).definition
    await case.bundle.definitions.save(SaveConnectorDefinition(definition=definition.model_copy(update={"tool_name_prefix": prefix})))


@pytest.mark.asyncio
@pytest.mark.parametrize(("personal_prefix", "shared_prefix"), (("Personal-tools", "Personal_tools"), ("__Personal", "Personal"), ("Personal", "Personal_read")))
async def test_unavailable_personal_namespace_blocks_normalized_shared_collisions(runtime_case: RuntimeCase, personal_prefix: str, shared_prefix: str) -> None:
    execution = await execution_case(runtime_case)
    execution.contexts.contexts.clear()
    await _prefix(runtime_case, "personal", personal_prefix)
    await install_shared_alias(runtime_case, True)
    await _prefix(runtime_case, "shared", shared_prefix)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    name = mangle_public_tool_name(shared_prefix, "read")
    assert await provider.is_personal_tool_name(name)
    for operation in (provider.list_tools(), provider.eligible_search_candidates(), provider.execute_tool(name, {"value": "same"})):
        with pytest.raises(ToolError, match="public_tool_name_conflict"):
            await operation
    assert execution.transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("personal_prefix", "native_prefix"), (("Personal-tools", "Personal_tools"), ("__Personal", "Personal"), ("Personal", "Personal_read")))
async def test_unavailable_personal_namespace_blocks_normalized_native_collisions(runtime_case: RuntimeCase, personal_prefix: str, native_prefix: str) -> None:
    execution = await execution_case(runtime_case)
    execution.contexts.contexts.clear()
    await _prefix(runtime_case, "personal", personal_prefix)
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    public = FastMCP("normalized-native", providers=[provider], middleware=[PersonalToolReservationMiddleware(provider)])
    name = mangle_public_tool_name(native_prefix, "read")
    calls: list[str] = []

    @public.tool(name=name)
    def alternate() -> str:
        calls.append("native")
        return "native"

    async with Client(public) as client:
        assert name not in {tool.name for tool in await client.list_tools()}
        assert (await client.call_tool(name, {}, raise_on_error=False)).is_error
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("first_prefix", "second_prefix"), (("Personal-tools", "Personal_tools"), ("__Personal", "Personal"), ("Personal", "Personal_read")))
async def test_unavailable_personal_definitions_with_overlapping_namespaces_are_ambiguous(runtime_case: RuntimeCase, first_prefix: str, second_prefix: str) -> None:
    execution = await execution_case(runtime_case)
    execution.contexts.contexts.clear()
    await _prefix(runtime_case, "personal", first_prefix)
    definition = (await runtime_case.bundle.definitions.get(ConnectorIdQuery(connector_id="personal"))).definition
    await runtime_case.bundle.definitions.save(SaveConnectorDefinition(definition=definition.model_copy(update={"connector_id": "other", "public_path": "/mcp/proxies/other", "tool_name_prefix": second_prefix})))
    provider = await provider_for(execution, PermitAllConnectorInvocationPolicy(), InvocationLog())
    with pytest.raises(ToolError, match="public_tool_name_conflict"):
        await provider.is_personal_tool_name(mangle_public_tool_name(second_prefix, "read"))
