from tests.umbod.core.downstream_mcp_connectors.personal_tools.runtime_support import CurrentContext, ExecutionCase
from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool
from umbod.core.capabilities import CapabilityIdentity
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import InMemoryPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalToolInventory, PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_tools import InvokePersonalTool, PersonalRuntimeContext, PersonalToolRuntime, PersonalToolRuntimeService
from umbod.core.connectors.downstream_mcp.personal_tools.service import PersonalToolDiscoveryService


async def execution_case(case: RuntimeCase) -> ExecutionCase:
    tool = approved_tool("read")
    contexts = CurrentContext(PersonalRuntimeContext(principal=case.query.key.principal, group_ids=case.query.group_ids))
    transport = InMemoryPersonalMcpTransport()
    transport.inventories[case.query.key] = PersonalToolInventory(tools=(tool,))
    transport.results[(case.query.key, "read")] = PersonalToolResult(result={"content": [], "structuredContent": {"owner": "owner"}})
    await PersonalToolDiscoveryService(case.store, case.bundle.personal_tool_access, transport, lambda: case.query.now).discover(case.query)
    runtime: PersonalToolRuntime = PersonalToolRuntimeService(contexts, case.bundle.definitions, case.bundle.personal_tool_access, transport, lambda: case.query.now)
    record = (await runtime.list_tools())[0]
    command = InvokePersonalTool(identity=CapabilityIdentity(connector_kind="downstream_mcp", connector_id="personal", capability_kind="tool", capability_key="read"), inventory_revision=record.inventory_revision, fingerprint=record.fingerprint, arguments={"value": "same"})
    return ExecutionCase(case, contexts, runtime, transport, command)
