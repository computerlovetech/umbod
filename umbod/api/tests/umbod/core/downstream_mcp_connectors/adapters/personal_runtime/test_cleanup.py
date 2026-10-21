import ssl
from datetime import datetime, timezone

import pytest
from fastmcp import Client

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import FastMCPPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime.http import PersonalHttpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import PersonalMcpTransport

from .conftest import ScriptedNetwork, ScriptedResolver


@pytest.mark.asyncio
async def test_bridge_cleanup_runs_even_when_sdk_client_close_raises(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, monkeypatch: pytest.MonkeyPatch) -> None:
    original_client_close = Client.close
    original_bridge_close = PersonalHttpTransport.aclose
    sdk_close_failed = False
    bridge_closed_after_failure = False

    async def failing_client_close(client: Client) -> None:
        nonlocal sdk_close_failed
        await original_client_close(client)
        sdk_close_failed = True
        raise RuntimeError("SDK cleanup failure sentinel")

    async def observed_bridge_close(bridge: PersonalHttpTransport) -> None:
        nonlocal bridge_closed_after_failure
        await original_bridge_close(bridge)
        if sdk_close_failed:
            bridge_closed_after_failure = True

    monkeypatch.setattr(Client, "close", failing_client_close)
    monkeypatch.setattr(PersonalHttpTransport, "aclose", observed_bridge_close)
    network.session = True
    transport: PersonalMcpTransport = FastMCPPersonalMcpTransport(
        limits, lambda: datetime.now(timezone.utc), ScriptedResolver(), lambda: network, ssl.create_default_context(),
    )
    with pytest.raises(PersonalRuntimeUnavailable, match="^Personal MCP unavailable$"):
        await transport.list_tools(target)
    assert sdk_close_failed
    assert bridge_closed_after_failure
