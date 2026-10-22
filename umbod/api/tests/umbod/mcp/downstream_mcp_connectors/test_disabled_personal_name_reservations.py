import pytest
from fastmcp import Client, FastMCP

from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import execution_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.mcp.downstream_mcp_connectors.test_personal_execution_pipeline import InvocationLog
from umbod.core.capabilities.descriptions import SystemConnectorCapabilityDescriptionOverrideStore
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.mcp.connectors.downstream_mcp import UnrestrictedDownstreamToolPermissionPolicy
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder
from umbod.mcp.public_app import _register_downstream_mcp_provider
from umbod.mcp.settings import MCPAppSettings, MCPSettings

__all__ = ["runtime_case"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("selection_enabled", "oauth_enabled"), ((False, True), (True, False), (False, False)))
async def test_disabled_personal_profile_keeps_private_namespace_reserved(runtime_case: RuntimeCase, selection_enabled: bool, oauth_enabled: bool) -> None:
    execution = await execution_case(runtime_case)
    settings = MCPAppSettings(mcp=MCPSettings(connector_tool_exposure_mode="flat", _env_file=None), _env_file=None)
    settings = settings.model_copy(update={"personal_connections": settings.personal_connections.model_copy(update={"enabled": selection_enabled, "oauth_enabled": oauth_enabled})})
    public = FastMCP("disabled-personal")
    public.capability_description_overrides = SystemConnectorCapabilityDescriptionOverrideStore()
    public.connector_tool_invocation_logger = InvocationLog()
    public.metrics_recorder = InMemoryMcpMetricsRecorder()
    await _register_downstream_mcp_provider(public, settings, UnrestrictedDownstreamToolPermissionPolicy(), runtime_case.database, PermitAllConnectorInvocationPolicy())
    alternate_calls: list[str] = []

    @public.tool(name="Personal_read")
    def alternate(value: str) -> str:
        alternate_calls.append(value)
        return "shared"

    @public.tool(name="Shared_read")
    def unrelated() -> str:
        return "shared"

    async with Client(public) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert "Personal_read" not in names
        assert "Shared_read" in names
        assert (await client.call_tool("Personal_read", {"value": "same"}, raise_on_error=False)).is_error
        assert not (await client.call_tool("Shared_read", {})).is_error
    assert alternate_calls == []
    assert execution.transport.calls == []
