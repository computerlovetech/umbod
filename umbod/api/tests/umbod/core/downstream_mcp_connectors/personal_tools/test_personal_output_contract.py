import pytest
from pydantic import ValidationError

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase, runtime_case
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool, enable_tool, replace_policy, save_matches
from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithOutputSchema
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalConnectionStore
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall, PersonalToolInventory, PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import PersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalToolRuntimeService, contract_fingerprint

from .runtime_support import execution_case

__all__ = ["runtime_case"]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ({"content": []}, {"content": [], "structuredContent": {}}, {"content": [], "structuredContent": {"value": 3}}, {"content": [], "structuredContent": None}))
async def test_approved_output_schema_requires_valid_structured_content(runtime_case: RuntimeCase, payload: dict[str, object]) -> None:
    execution = await execution_case(runtime_case)
    tool = DiscoveredToolWithOutputSchema(**approved_tool("read").model_dump(exclude={"output_schema_status"}), output_schema={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]})
    policy = await replace_policy(runtime_case, (tool,))
    await enable_tool(runtime_case, "read")
    await save_matches(runtime_case, policy)
    execution.transport.inventories[runtime_case.query.key] = PersonalToolInventory(tools=(tool,))
    execution.transport.results[(runtime_case.query.key, "read")] = PersonalToolResult(result=payload)
    command = execution.command.model_copy(update={"inventory_revision": (await execution.runtime.list_tools())[0].inventory_revision, "fingerprint": contract_fingerprint(tool)})
    with pytest.raises(PersonalRuntimeUnavailable, match="^Personal tool unavailable$"):
        await execution.runtime.execute(command)
    assert len(execution.transport.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", ({}, {"_meta": {}}, {"_meta": {"vendor": {"trace": ["valid"]}}}))
async def test_absent_structured_content_is_explicitly_allowed_without_output_schema(runtime_case: RuntimeCase, metadata: dict[str, object]) -> None:
    execution = await execution_case(runtime_case)
    payload = {"content": [], **metadata}
    execution.transport.results[(runtime_case.query.key, "read")] = PersonalToolResult(result=payload)
    assert (await execution.runtime.execute(execution.command)).result == payload


@pytest.mark.parametrize("metadata", (None, [], "invalid", 1))
def test_personal_port_result_rejects_nonobject_metadata(metadata: object) -> None:
    with pytest.raises(ValidationError, match="Result metadata must be a JSON object"):
        PersonalToolResult(result={"content": [], "_meta": metadata})


@pytest.mark.asyncio
async def test_approved_local_output_references_validate_offline(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    tool = DiscoveredToolWithOutputSchema(**approved_tool("read").model_dump(exclude={"output_schema_status"}), output_schema={"$defs": {"text": {"type": "string"}}, "type": "object", "properties": {"value": {"$ref": "#/$defs/text"}}, "required": ["value"]})
    policy = await replace_policy(runtime_case, (tool,))
    await enable_tool(runtime_case, "read")
    await save_matches(runtime_case, policy)
    execution.transport.inventories[runtime_case.query.key] = PersonalToolInventory(tools=(tool,))
    execution.transport.results[(runtime_case.query.key, "read")] = PersonalToolResult(result={"content": [], "structuredContent": {"value": "valid"}})
    command = execution.command.model_copy(update={"inventory_revision": (await execution.runtime.list_tools())[0].inventory_revision, "fingerprint": contract_fingerprint(tool)})
    assert (await execution.runtime.execute(command)).result["structuredContent"] == {"value": "valid"}


class DisconnectingTransport:
    def __init__(self, transport: PersonalMcpTransport, connections: PersonalConnectionStore) -> None:
        self._transport = transport
        self._connections = connections

    async def list_tools(self, target: PersonalRuntimeTarget) -> PersonalToolInventory:
        return await self._transport.list_tools(target)

    async def call_tool(self, command: PersonalToolCall) -> PersonalToolResult:
        result = await self._transport.call_tool(command)
        await self._connections.disconnect(command.target.key)
        return result


@pytest.mark.asyncio
async def test_operation_admitted_before_invalidation_can_finish_but_next_call_cannot(runtime_case: RuntimeCase) -> None:
    execution = await execution_case(runtime_case)
    runtime = PersonalToolRuntimeService(execution.contexts, runtime_case.bundle.definitions, runtime_case.bundle.personal_tool_access, DisconnectingTransport(execution.transport, runtime_case.bundle.personal_connections), lambda: runtime_case.query.now)
    assert (await runtime.execute(execution.command)).result["structuredContent"] == {"owner": "owner"}
    with pytest.raises(PersonalRuntimeUnavailable):
        await runtime.execute(execution.command)
    assert len(execution.transport.calls) == 1
