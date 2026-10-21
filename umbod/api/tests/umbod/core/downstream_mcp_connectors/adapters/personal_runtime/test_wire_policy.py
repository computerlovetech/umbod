import json
from datetime import datetime, timezone

import anyio
import httpx2
from .contracts import LOOKUP_FINGERPRINT
import pytest

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime.operation import OperationState
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall


def request(target: PersonalRuntimeTarget, method: str, body: object) -> httpx2.Request:
    return httpx2.Request(method, target.endpoint_url, headers={"Authorization": f"Bearer {target.access_token.get_secret_value()}"}, content=json.dumps(body).encode() if body else b"")


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["duplicate-call", "reconnect", "resume", "query", "sni", "batch", "task", "meta", "elicitation", "initialize", "delete", "changed-arguments", "implicit-list"])
async def test_wire_state_latches_and_cancels_before_disallowed_request(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, violation: str) -> None:
    command = PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={})
    with anyio.CancelScope() as scope:
        state = OperationState(target, limits, lambda: datetime.now(timezone.utc), scope, command)
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        notify = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "lookup", "arguments": {}}}
        listing = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}
        for body in (init, notify, listing):
            outgoing = request(target, "POST", body)
            state.authorize(outgoing, outgoing.content)
        state.preflight_complete = True
        outgoing = request(target, "POST", call)
        state.authorize(outgoing, outgoing.content)
        outgoing = request(target, "POST", {**call, "id": 99})
        if violation == "reconnect":
            outgoing = request(target, "GET", {})
            state.authorize(outgoing, b"")
        elif violation == "resume":
            outgoing = request(target, "GET", {})
            outgoing.headers["Last-Event-ID"] = "resume"
        elif violation == "query":
            outgoing.url = httpx2.URL(target.endpoint_url + "&override=1")
        elif violation == "sni":
            outgoing.extensions["sni_hostname"] = "evil.example"
        elif violation == "batch":
            outgoing = request(target, "POST", [call])
        elif violation in {"task", "meta", "changed-arguments"}:
            extra = {"task": {}} if violation == "task" else {"_meta": {"outer": "secret"}}
            if violation == "changed-arguments":
                extra = {"arguments": {"different": True}}
            outgoing = request(target, "POST", {**call, "params": {**call["params"], **extra}})
        elif violation == "implicit-list":
            outgoing = request(target, "POST", {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
        elif violation == "elicitation":
            outgoing = request(target, "POST", {"jsonrpc": "2.0", "id": 88, "result": {"action": "accept"}})
        elif violation == "initialize":
            outgoing = request(target, "POST", init)
        elif violation == "delete":
            outgoing = request(target, "DELETE", {})
            state.authorize(outgoing, b"")
        with pytest.raises(PersonalRuntimeUnavailable):
            state.authorize(outgoing, outgoing.content)
        assert state.failed
        assert scope.cancel_called
