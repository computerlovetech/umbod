import pytest

from tests.umbod.core.downstream_mcp_connectors.test_personal_authorization_health import health_query
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolInventory, PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolDiscoveryService

from .runtime_support import execution_case

__all__ = ["runtime_case"]


@pytest.mark.asyncio
@pytest.mark.parametrize("specific", [True, False])
async def test_execution_records_only_specific_admitted_rejections(runtime_case: RuntimeCase, monkeypatch: pytest.MonkeyPatch, specific: bool) -> None:
    execution = await execution_case(runtime_case)

    async def failing_call(command: PersonalToolCall) -> PersonalToolResult:
        if specific:
            raise PersonalAuthorizationRejected("Personal MCP unavailable")
        raise PersonalRuntimeUnavailable("Personal MCP unavailable")

    monkeypatch.setattr(execution.transport, "call_tool", failing_call)
    with pytest.raises(PersonalRuntimeUnavailable):
        await execution.runtime.execute(execution.command)
    health = await runtime_case.bundle.personal_authorization_health.get(health_query(runtime_case))
    assert health.state == ("reconnect_required" if specific else "authorized")
    assert len(await execution.runtime.list_tools()) == (0 if specific else 1)
    if specific:
        with pytest.raises(PersonalRuntimeUnavailable):
            await execution.runtime.execute(execution.command)
        with pytest.raises(PersonalRuntimeUnavailable):
            await runtime_case.store.resolve(runtime_case.query)


@pytest.mark.asyncio
@pytest.mark.parametrize("specific", [True, False])
async def test_discovery_records_only_resolved_target_rejections(runtime_case: RuntimeCase, monkeypatch: pytest.MonkeyPatch, specific: bool) -> None:
    execution = await execution_case(runtime_case)

    async def failing_list(target: PersonalRuntimeTarget) -> PersonalToolInventory:
        if specific:
            raise PersonalAuthorizationRejected("Personal MCP unavailable")
        raise PersonalRuntimeUnavailable("Personal MCP unavailable")

    monkeypatch.setattr(execution.transport, "list_tools", failing_list)
    discovery = PersonalToolDiscoveryService(runtime_case.bundle.personal_tool_policies, runtime_case.store, runtime_case.bundle.personal_tool_access, execution.transport, lambda: runtime_case.query.now)
    with pytest.raises(PersonalRuntimeUnavailable):
        await discovery.discover(runtime_case.query)
    assert (await runtime_case.bundle.personal_authorization_health.get(health_query(runtime_case))).state == ("reconnect_required" if specific else "authorized")
    if specific:
        with pytest.raises(PersonalRuntimeUnavailable):
            await discovery.discover(runtime_case.query)
