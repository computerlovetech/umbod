from .contracts import LOOKUP_FINGERPRINT
import json
import logging

import pytest

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall

from .conftest import ScriptedNetwork, ScriptedResolver, make_transport


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ("invalid_envelope", "invalid_json", "unicode_escape", "valid_echo", "sse_echo", "sse_id", "sse_bom", "sse_unterminated", "header"))
async def test_untrusted_credentials_never_reach_sdk_diagnostics(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, caplog: pytest.LogCaptureFixture, mode: str) -> None:
    caplog.set_level(logging.DEBUG)
    token = target.access_token.get_secret_value()
    packet: dict[str, object] = {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": token}]}}
    if mode in {"invalid_envelope", "unicode_escape", "sse_bom"}:
        packet["jsonrpc"] = token
    body = json.dumps(packet)
    if mode in {"unicode_escape", "sse_bom"}:
        body = body.replace("a", "\\u0061")
    if mode == "invalid_json":
        body = '{"jsonrpc":"' + token
    if mode.startswith("sse_"):
        network.call_response_headers["content-type"] = "text/event-stream"
        network.read_size = 3
        if mode == "sse_id":
            body = "id: " + token + "\n\n"
        elif mode == "sse_unterminated":
            body = "data: " + body
        else:
            body = ("\ufeff" if mode == "sse_bom" else "") + "data: " + body + "\r\n\r\n"
    network.raw_body = body.encode()
    if mode == "header":
        network.response_headers["mcp-session-id"] = token
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable) as failure:
        await transport.call_tool(PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={}))
    assert token not in str(failure.value)
    assert token not in caplog.text
    assert sum(message.get("method") == "tools/call" for _, _, message in network.requests) == (0 if mode == "header" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("charset", ("utf-7", "latin-1", "utf-16"))
async def test_sdk_cannot_decode_with_a_different_charset(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, caplog: pytest.LogCaptureFixture, charset: str) -> None:
    network.call_response_headers["content-type"] = "text/event-stream; charset=" + charset
    token = target.access_token.get_secret_value()
    network.raw_body = ('data: {"jsonrpc":"' + token + '"}\n\n').encode()
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.call_tool(PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={}))
    assert token not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("separator", ("\n", "\r", "\r\n"))
async def test_valid_fragmented_sse_is_preserved(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, separator: str) -> None:
    network.call_response_headers["content-type"] = "text/event-stream"
    network.read_size = 2
    message = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "safe"}]}})
    network.raw_body = ("data: " + message + separator + separator).encode()
    transport = make_transport(limits, network, ScriptedResolver())
    result = await transport.call_tool(PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={}))
    assert result.result["content"] == [{"type": "text", "text": "safe"}]
