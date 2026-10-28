import pytest
from fastmcp import Client

from tests.umbod.mcp.downstream_mcp_connectors.personal_runtime_support import execution_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from umbod.core.connectors.native.runtime import ConnectorRuntime
from umbod.core.persistence import Database
from umbod.mcp.public_app import build_mcp
from umbod.mcp.settings import MCPAppSettings, MCPSettings

__all__ = ["runtime_case"]


class BorrowedDatabaseRuntime:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.readiness = self

    async def ensure_ready(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize(("selection_enabled", "oauth_enabled"), ((False, True), (True, False), (False, False)))
async def test_disabled_personal_profile_keeps_private_namespace_reserved(runtime_case: RuntimeCase, selection_enabled: bool, oauth_enabled: bool) -> None:
    execution = await execution_case(runtime_case)
    settings = MCPAppSettings(mcp=MCPSettings(connector_tool_exposure_mode="flat", _env_file=None), _env_file=None)
    settings = settings.model_copy(update={"personal_connections": settings.personal_connections.model_copy(update={"enabled": selection_enabled, "oauth_enabled": oauth_enabled})})
    public = await build_mcp(
        settings, None,
        ConnectorRuntime(connector_registrations=(), connector_configuration_store=None, connector_publishing_store=None, connector_tool_mappings=()),
        BorrowedDatabaseRuntime(runtime_case.database),
    )
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
