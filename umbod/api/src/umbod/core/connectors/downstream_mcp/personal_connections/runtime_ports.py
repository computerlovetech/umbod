from typing import Protocol

from umbod.core.connectors.downstream_mcp.personal_connections.health_models import RejectPersonalAuthorization

from .runtime_models import PersonalRuntimeAuthorizationQuery, PersonalRuntimeTarget, PersonalToolCall, PersonalToolInventory, PersonalToolResult


class PersonalRuntimeAuthorizationStore(Protocol):
    async def reject_authorization(self, command: RejectPersonalAuthorization) -> None: ...

    async def resolve(self, query: PersonalRuntimeAuthorizationQuery) -> PersonalRuntimeTarget: ...


class PersonalMcpTransport(Protocol):
    async def list_tools(self, target: PersonalRuntimeTarget) -> PersonalToolInventory: ...

    async def call_tool(self, command: PersonalToolCall) -> PersonalToolResult: ...
