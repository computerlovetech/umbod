
from .contracts import LOOKUP_FINGERPRINT
import pytest

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall

from .conftest import ScriptedNetwork, ScriptedResolver, make_transport


@pytest.mark.asyncio
async def test_sse_resumption_is_refused_without_replaying_call(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.stream_call = True
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.call_tool(PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={}))
    assert len([body for _, _, body in network.requests if body.get("method") == "tools/call"]) == 1
    assert not any("last-event-id" in headers for _, headers, _ in network.requests)


@pytest.mark.asyncio
async def test_initial_background_get_and_termination_are_allowed(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.session = True
    transport = make_transport(limits, network, ScriptedResolver())
    await transport.list_tools(target)
    assert [method for method, _, _ in network.requests].count("GET") == 1
    assert [method for method, _, _ in network.requests].count("DELETE") == 1
    assert all(body.get("params", {}).get("_meta", {}) == {} for _, _, body in network.requests)


@pytest.mark.asyncio
async def test_background_get_reconnection_is_latched(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.session = True
    network.close_get = True
    network.tool_delay = 1.5
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(target)
    assert [method for method, _, _ in network.requests].count("GET") == 1
