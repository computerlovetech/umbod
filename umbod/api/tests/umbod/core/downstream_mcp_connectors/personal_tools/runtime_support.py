from dataclasses import dataclass

from tests.umbod.core.downstream_mcp_connectors.test_personal_runtime_authorizations import RuntimeCase
from tests.umbod.core.downstream_mcp_connectors.test_personal_tools_s3_contracts import approved_tool, enable_tool, replace_policy, save_matches
from umbod.core.capabilities import CapabilityIdentity
from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import InMemoryPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable, PersonalToolInventory, PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_tools import InvokePersonalTool, PersonalRuntimeContext, PersonalToolRuntime, PersonalToolRuntimeService, contract_fingerprint


class CurrentContext:
    def __init__(self, context: PersonalRuntimeContext) -> None:
        self.contexts: list[PersonalRuntimeContext] = [context]

    async def get_context(self) -> PersonalRuntimeContext:
        if not self.contexts:
            raise PersonalRuntimeUnavailable("Personal identity unavailable")
        return self.contexts[0]


@dataclass(frozen=True)
class ExecutionCase:
    case: RuntimeCase
    contexts: CurrentContext
    runtime: PersonalToolRuntime
    transport: InMemoryPersonalMcpTransport
    command: InvokePersonalTool


async def execution_case(case: RuntimeCase) -> ExecutionCase:
    tool = approved_tool("read")
    policy = await replace_policy(case, (tool,))
    await enable_tool(case, "read")
    await save_matches(case, policy)
    contexts = CurrentContext(PersonalRuntimeContext(principal=case.query.key.principal, group_ids=case.query.group_ids))
    transport = InMemoryPersonalMcpTransport()
    transport.inventories[case.query.key] = PersonalToolInventory(tools=(tool,))
    transport.results[(case.query.key, "read")] = PersonalToolResult(result={"content": [], "structuredContent": {"owner": "owner"}})
    runtime: PersonalToolRuntime = PersonalToolRuntimeService(contexts, case.bundle.definitions, case.bundle.personal_tool_access, transport, lambda: case.query.now)
    command = InvokePersonalTool(identity=CapabilityIdentity(connector_kind="downstream_mcp", connector_id="personal", capability_kind="tool", capability_key="read"), contract_revision=policy.revision, fingerprint=contract_fingerprint(tool), arguments={"value": "same"})
    return ExecutionCase(case, contexts, runtime, transport, command)
