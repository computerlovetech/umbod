
from .contracts import LOOKUP_FINGERPRINT, LOOKUP_TOOL
import pytest

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import InMemoryPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.models import CanonicalPrincipal
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolInventory, PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import PersonalMcpTransport



@pytest.mark.asyncio
async def test_inmemory_is_scoped_by_owner(target: PersonalRuntimeTarget) -> None:
    adapter = InMemoryPersonalMcpTransport()
    adapter.inventories[target.key] = PersonalToolInventory(tools=(LOOKUP_TOOL,))
    adapter.results[(target.key, "lookup")] = PersonalToolResult(result={"ok": True})
    transport: PersonalMcpTransport = adapter
    assert (await transport.list_tools(target)).tools == (LOOKUP_TOOL,)
    command = PersonalToolCall(target=target, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={})
    assert (await transport.call_tool(command)).result == {"ok": True}
    assert adapter.calls == [command]
    other = target.model_copy(update={"key": target.key.model_copy(update={"principal": CanonicalPrincipal(namespace="test", subject="bob")})})
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(other)
