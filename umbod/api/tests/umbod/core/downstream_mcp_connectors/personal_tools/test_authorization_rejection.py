from tests.umbod.core.downstream_mcp_connectors.personal_discovery_support import read_available

import pytest

from tests.umbod.core.downstream_mcp_connectors.test_personal_authorization_health import health_query
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolInventory, PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import PersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolDiscoveryService, PersonalToolRuntimeService

from .runtime_support import execution_case

__all__ = ["runtime_case"]


class FaultPersonalMcpTransport(PersonalMcpTransport):
    def __init__(self, error: PersonalRuntimeUnavailable) -> None:
        self._error = error

    async def list_tools(self, target: PersonalRuntimeTarget) -> PersonalToolInventory:
        raise self._error

    async def call_tool(self, command: PersonalToolCall) -> PersonalToolResult:
        raise self._error


@pytest.mark.asyncio
@pytest.mark.parametrize("specific", [True, False])
async def test_execution_records_only_specific_admitted_rejections(runtime_case: RuntimeCase, specific: bool) -> None:
    execution = await execution_case(runtime_case)
    error = PersonalAuthorizationRejected("Personal MCP unavailable") if specific else PersonalRuntimeUnavailable("Personal MCP unavailable")
    transport = FaultPersonalMcpTransport(error)
    runtime = PersonalToolRuntimeService(execution.caller, runtime_case.bundle.personal_tool_access, transport, lambda: runtime_case.query.now)
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime.execute(execution.command)
    health = await runtime_case.bundle.personal_authorization_health.get(health_query(runtime_case))
    assert health.state == ("reconnect_required" if specific else "authorized")
    assert len(await read_available(runtime_case.bundle, runtime_case.query)) == (0 if specific else 1)
    if specific:
        with pytest.raises(PersonalRuntimeUnavailable):
            await runtime.execute(execution.command)
        with pytest.raises(PersonalRuntimeUnavailable):
            await runtime_case.store.resolve(runtime_case.query)


@pytest.mark.asyncio
@pytest.mark.parametrize("specific", [True, False])
async def test_discovery_records_only_resolved_target_rejections(runtime_case: RuntimeCase, specific: bool) -> None:
    await execution_case(runtime_case)
    error = PersonalAuthorizationRejected("Personal MCP unavailable") if specific else PersonalRuntimeUnavailable("Personal MCP unavailable")
    transport = FaultPersonalMcpTransport(error)
    discovery = PersonalToolDiscoveryService(runtime_case.store, runtime_case.bundle.personal_tool_access, transport, lambda: runtime_case.query.now)
    with pytest.raises(PersonalRuntimeUnavailable):
        await discovery.discover(runtime_case.query)
    assert (await runtime_case.bundle.personal_authorization_health.get(health_query(runtime_case))).state == ("reconnect_required" if specific else "authorized")
    if specific:
        with pytest.raises(PersonalRuntimeUnavailable):
            await discovery.discover(runtime_case.query)
