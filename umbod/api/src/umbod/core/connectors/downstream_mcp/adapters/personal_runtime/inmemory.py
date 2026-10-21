from umbod.core.connectors.downstream_mcp.personal_connections.models import PersonalConnectionKey
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import (
    PersonalRuntimeTarget,
    PersonalRuntimeUnavailable,
    PersonalToolCall,
    PersonalToolInventory,
    PersonalToolResult,
)


from umbod.core.connectors.downstream_mcp.personal_tools.contract_validation import contract_fingerprint


class InMemoryPersonalMcpTransport:
    def __init__(self) -> None:
        self.inventories: dict[PersonalConnectionKey, PersonalToolInventory] = {}
        self.results: dict[tuple[PersonalConnectionKey, str], PersonalToolResult] = {}
        self.calls: list[PersonalToolCall] = []
        self.list_requests: list[PersonalRuntimeTarget] = []

    async def list_tools(self, target: PersonalRuntimeTarget) -> PersonalToolInventory:
        self.list_requests.append(target)
        if target.key not in self.inventories:
            raise PersonalRuntimeUnavailable("Personal MCP unavailable")
        return self.inventories[target.key]

    async def call_tool(self, command: PersonalToolCall) -> PersonalToolResult:
        inventory = await self.list_tools(command.target)
        matches = tuple(tool for tool in inventory.tools if tool.identity.downstream_name == command.tool_name)
        if len(matches) != 1 or contract_fingerprint(matches[0]) != command.expected_fingerprint:
            raise PersonalRuntimeUnavailable("Personal MCP unavailable")
        self.calls.append(command)
        key = (command.target.key, command.tool_name)
        if key not in self.results:
            raise PersonalRuntimeUnavailable("Personal MCP unavailable")
        return self.results[key]
