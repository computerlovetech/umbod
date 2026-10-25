from umbod.core.connectors.downstream_mcp.personal_connections import PersonalCaller, UnavailablePersonalCaller
from tests.umbod.core.downstream_mcp_connectors.personal_caller_support import captured_personal_caller
from dataclasses import dataclass

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool
from umbod.core.capabilities import CapabilityIdentity
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import InMemoryPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalToolInventory, PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_tools import InvokePersonalTool, PersonalToolRuntime, PersonalToolRuntimeService, SavePersonalToolObservation, contract_fingerprint


@dataclass(frozen=True)
class ExecutionCase:
    case: RuntimeCase
    caller: PersonalCaller
    runtime: PersonalToolRuntime
    transport: InMemoryPersonalMcpTransport
    command: InvokePersonalTool


def runtime_for_caller(execution: ExecutionCase, caller: PersonalCaller | UnavailablePersonalCaller) -> PersonalToolRuntime:
    case = execution.case
    return PersonalToolRuntimeService(caller, case.bundle.definitions, case.bundle.personal_tool_access, execution.transport, lambda: case.query.now)


async def execution_case(case: RuntimeCase) -> ExecutionCase:
    tool = approved_tool("read")
    target = await case.store.resolve(case.query)
    await case.bundle.personal_tool_access.save_observation(SavePersonalToolObservation(query=case.query, target=target, expected_inventory_revision=await case.bundle.personal_tool_access.read_inventory_revision(case.query), tools=(tool,), expires_at=target.expires_at))
    record = (await case.bundle.personal_tool_access.list_available(case.query))[0]
    caller = captured_personal_caller(case.query.key.principal, case.query.group_ids)
    transport = InMemoryPersonalMcpTransport()
    transport.inventories[case.query.key] = PersonalToolInventory(tools=(tool,))
    transport.results[(case.query.key, "read")] = PersonalToolResult(result={"content": [], "structuredContent": {"owner": "owner"}})
    runtime: PersonalToolRuntime = PersonalToolRuntimeService(caller, case.bundle.definitions, case.bundle.personal_tool_access, transport, lambda: case.query.now)
    command = InvokePersonalTool(identity=CapabilityIdentity(connector_kind="downstream_mcp", connector_id="personal", capability_kind="tool", capability_key="read"), inventory_revision=record.inventory_revision, fingerprint=contract_fingerprint(tool), arguments={"value": "same"})
    return ExecutionCase(case, caller, runtime, transport, command)
