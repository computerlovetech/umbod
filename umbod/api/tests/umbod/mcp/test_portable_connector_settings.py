from pathlib import Path

import pytest
from fastmcp import Client

from tests.mcp_fixtures import build_test_mcp, empty_connector_plugins
from umbod.core.system_settings import (
    UpdatePortableConnectorSettings,
    create_system_settings_service,
)
from umbod.mcp import runtime_options
from umbod.mcp.settings import MCPAppSettings, MCPSettings


@pytest.mark.asyncio
async def test_enabling_portable_connectors_does_not_change_public_tool_discovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    availability = tmp_path / "availability.json"
    availability.write_text('{"connectors":[]}', encoding="utf-8")
    monkeypatch.setenv(
        "UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability)
    )
    monkeypatch.setattr(
        runtime_options, "load_connector_plugins", empty_connector_plugins
    )
    settings = MCPAppSettings(mcp=MCPSettings(connector_tool_exposure_mode="codemode"))
    server = await build_test_mcp(settings)
    runtime = server.persistence_runtime
    try:
        async with Client(server) as client:
            disabled_tools = await client.list_tools()
        await create_system_settings_service(
            runtime.database
        ).set_portable_connectors_enabled(
            "administrator",
            UpdatePortableConnectorSettings(portable_connectors_enabled=True),
        )
        async with Client(server) as client:
            enabled_tools = await client.list_tools()

        assert "execute_code" in {tool.name for tool in disabled_tools}
        assert enabled_tools == disabled_tools
    finally:
        await runtime.shutdown()
