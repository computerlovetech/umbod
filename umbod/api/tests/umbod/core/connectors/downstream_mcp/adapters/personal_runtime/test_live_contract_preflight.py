import pytest

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall

from .conftest import ScriptedNetwork, ScriptedResolver, make_transport
from .contracts import LOOKUP_FINGERPRINT


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ("missing", "duplicate", "input", "output", "annotations", "execution", "invalid"))
async def test_live_contract_drift_never_sends_side_effecting_call(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, drift: str) -> None:
    if drift == "missing":
        network.tools = []
    elif drift == "duplicate":
        network.tools *= 2
    elif drift == "input":
        network.tools[0]["inputSchema"] = {"type": "object", "required": ["changed"]}
    elif drift == "output":
        network.tools[0]["outputSchema"] = {"type": "object"}
    elif drift == "annotations":
        network.tools[0]["annotations"] = {"readOnlyHint": False}
    elif drift == "execution":
        network.tools[0]["execution"] = {"taskSupport": "required"}
    else:
        network.tools[0]["inputSchema"] = {"type": "invalid"}
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.call_tool(PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={}))
    assert not any(body.get("method") == "tools/call" for _, _, body in network.requests)


@pytest.mark.asyncio
async def test_preflight_paginates_in_same_session_before_exactly_one_call(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.session = True
    network.tool_pages = [[{"name": "unrelated", "inputSchema": {"type": "object"}}], network.tools]
    network.cursor_sequence = ["next", ""]
    transport = make_transport(limits, network, ScriptedResolver())
    result = await transport.call_tool(PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={}))
    messages = [(headers, body) for _, headers, body in network.requests if body.get("method") in {"tools/list", "tools/call"}]
    assert [body["method"] for _, body in messages] == ["tools/list", "tools/list", "tools/call"]
    assert messages[1][1]["params"] == {"cursor": "next", "_meta": {}}
    assert all(headers["mcp-session-id"] == "fixture-session" for headers, _ in messages)
    assert result.result["content"] == [{"type": "text", "text": "done"}]
    assert sum(body.get("method") == "initialize" for _, _, body in network.requests) == 1


@pytest.mark.asyncio
async def test_preflight_duplicate_across_pages_fails_before_call(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork) -> None:
    network.cursor_sequence = ["next", ""]
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.call_tool(PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={}))
    assert not any(body.get("method") == "tools/call" for _, _, body in network.requests)
