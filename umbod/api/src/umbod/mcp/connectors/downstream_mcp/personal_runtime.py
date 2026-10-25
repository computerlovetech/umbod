from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.middleware.authorization import _requested_version
from fastmcp.tools import Tool, ToolResult

from fastmcp.server.auth import AuthContext
from fastmcp.server.dependencies import get_access_token, get_server

from umbod.config.app import AppConfig
from umbod.core.connectors.downstream_mcp.adapters.identity import authenticated_personal_mcp_claims, personal_identity_facts, personal_group_membership
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
from umbod.core.callers import AuthenticationProvenance
from umbod.core.connectors.downstream_mcp.personal_connections.caller import PersonalCaller, PersonalCallerProvider, UnavailablePersonalCaller
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalToolResult
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import PersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_tools import InvokePersonalTool, PersonalToolRecord, PersonalToolRuntimeService
from umbod.core.connectors.downstream_mcp.personal_tools.ports import PersonalToolAccessStore
from umbod.core.connectors.downstream_mcp.stores.ports import ConnectorDefinitionStore
from umbod.core.connectors.downstream_mcp.personal_connections.identity_models import ResolvedPersonalIdentity
from umbod.mcp.auth.caller import authentication_provenance, caller_context_from_access_token
from umbod.core.connectors.downstream_mcp.personal_connections.principal import canonical_principal

from .tool_invocation import AuthorizedPersonalTool


class McpPersonalCallerProvider:
    def __init__(self, settings: AppConfig) -> None:
        self._settings = settings
        self._policy = personal_identity_policy_from_app_config(settings)

    async def get_caller(self) -> PersonalCaller | UnavailablePersonalCaller:
        token = get_access_token()
        authentication = AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
        try:
            provider = getattr(get_server(), "auth", None)
            if provider is not None:
                authentication = authentication_provenance(provider)
        except RuntimeError:
            pass
        caller = caller_context_from_access_token(token, authentication)
        if caller.authentication == AuthenticationProvenance.UNAVAILABLE or token is None or not isinstance(token.claims, Mapping):
            return UnavailablePersonalCaller(kind="unavailable")
        claims = authenticated_personal_mcp_claims(self._settings, self._policy, token.claims)
        resolution = canonical_principal(self._policy, personal_identity_facts(claims))
        if not isinstance(resolution, ResolvedPersonalIdentity):
            return UnavailablePersonalCaller(kind="unavailable")
        return PersonalCaller(
            caller=caller, principal=resolution.principal,
            groups=personal_group_membership(claims.get(self._settings.mcp.permission_group_claim)),
        )


class McpPersonalToolRuntime:
    def __init__(
        self,
        callers: PersonalCallerProvider,
        definitions: ConnectorDefinitionStore,
        access: PersonalToolAccessStore,
        transport: PersonalMcpTransport,
        clock: Callable[[], datetime],
    ) -> None:
        self._callers = callers
        self._definitions = definitions
        self._access = access
        self._transport = transport
        self._clock = clock

    async def _operation(self) -> PersonalToolRuntimeService:
        caller = await self._callers.get_caller()
        return PersonalToolRuntimeService(caller, self._definitions, self._access, self._transport, self._clock)

    async def list_tools(self) -> tuple[PersonalToolRecord, ...]:
        operation = await self._operation()
        return await operation.list_tools()

    async def execute(self, command: InvokePersonalTool) -> PersonalToolResult:
        operation = await self._operation()
        return await operation.execute(command)


class PersonalToolNamespace(Protocol):
    async def is_personal_tool_name(self, name: str) -> bool: ...


class PersonalToolReservationMiddleware(Middleware):
    def __init__(self, claims: PersonalToolNamespace) -> None:
        self._claims = claims

    async def _allows(self, tool: Tool) -> bool:
        reserved = await self._claims.is_personal_tool_name(tool.name)
        if isinstance(tool, AuthorizedPersonalTool):
            return reserved and await tool.is_authorized()
        return not reserved

    async def on_list_tools(self, context: MiddlewareContext[mt.ListToolsRequest], call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]]) -> Sequence[Tool]:
        tools = await call_next(context)
        authorized: list[Tool] = []
        for tool in tools:
            if not await self._allows(tool):
                continue
            if await self._claims.is_personal_tool_name(tool.name):
                runtime = context.fastmcp_context
                if runtime is None:
                    continue
                resolved = await runtime.fastmcp.get_tool(tool.name, version=_requested_version({"fastmcp": {"version": tool.version}}))
                if resolved is None or not await self._allows(resolved):
                    continue
            authorized.append(tool)
        return authorized

    async def on_call_tool(self, context: MiddlewareContext[mt.CallToolRequestParams], call_next: CallNext[mt.CallToolRequestParams, ToolResult]) -> ToolResult:
        if not await self._claims.is_personal_tool_name(context.message.name):
            return await call_next(context)
        runtime = context.fastmcp_context
        if runtime is None:
            raise ToolError("Tool is not available")
        tool = await runtime.fastmcp.get_tool(context.message.name, version=_requested_version(context.message.meta))
        if tool is None or not await self._allows(tool):
            raise ToolError("Tool is not available")
        return await call_next(context)


def personal_tool_permission_check(legacy: Callable[[AuthContext], bool]) -> Callable[[AuthContext], Awaitable[bool]]:
    async def check(context: AuthContext) -> bool:
        if isinstance(context.component, AuthorizedPersonalTool):
            return await context.component.is_authorized()
        return legacy(context)
    return check
