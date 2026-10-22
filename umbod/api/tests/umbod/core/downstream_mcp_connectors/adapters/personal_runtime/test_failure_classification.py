from datetime import datetime, timezone

import pytest

from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalAuthorizationRejected, PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall

from .conftest import ScriptedNetwork, ScriptedResolver, make_transport
from .contracts import LOOKUP_FINGERPRINT


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,reason", [("expired", "target_expired"), ("deadline", "timeout"), ("wire_policy", "transport_failure"), ("forbidden", "transport_failure"), ("rejected", "authorization_rejected"), ("missing", "contract_mismatch"), ("changed", "contract_mismatch"), ("malformed", "transport_failure")])
async def test_transport_failures_use_typed_evidence_not_cancellation_or_content(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, failure: str, reason: str) -> None:
    if failure == "expired":
        target = target.model_copy(update={"expires_at": datetime.now(timezone.utc)})
    elif failure == "deadline":
        limits = limits.model_copy(update={"operation_timeout_seconds": 0.05})
        network.delay = 2
    elif failure == "wire_policy":
        network.response_headers = {"content-encoding": "gzip"}
    elif failure in {"rejected", "forbidden"}:
        network.status = 401 if failure == "rejected" else 403
        network.response_headers = {"content-type": "invalid/header-sentinel", "www-authenticate": "timeout contract_mismatch"}
        network.session = True
        network.cleanup_status = 500
    elif failure == "missing":
        network.tools = []
    elif failure == "changed":
        network.tools[0]["inputSchema"] = {"type": "object", "required": ["changed"]}
    else:
        network.tools[0]["inputSchema"] = []
    transport = make_transport(limits, network, ScriptedResolver())
    command = PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={})
    with pytest.raises(PersonalRuntimeUnavailable) as caught:
        await transport.call_tool(command)
    assert caught.value.diagnostic.reason == reason
    assert caught.value.diagnostic.execution_mode == "personal"
    assert isinstance(caught.value, PersonalAuthorizationRejected) == (failure == "rejected")
    assert caught.value.__context__ is None
    assert str(caught.value) == "Personal MCP unavailable"
    assert not any(body.get("method") == "tools/call" for _, _, body in network.requests)
