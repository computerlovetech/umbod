from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Protocol

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.middleware.authorization import _requested_version
from fastmcp.tools import Tool, ToolResult

from fastmcp.server.auth import AuthContext
from fastmcp.server.dependencies import get_access_token

from umbod.config.app import AppConfig
from umbod.core.connectors.downstream_mcp.adapters.identity import authenticated_personal_mcp_claims, personal_identity_facts, personal_group_membership
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
from umbod.core.connectors.downstream_mcp.personal_connections.identity_models import PersonalIdentityPolicy, ResolvedPersonalIdentity
from umbod.core.connectors.downstream_mcp.personal_connections.principal import canonical_principal
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalRuntimeContext

from .tool_invocation import AuthorizedPersonalTool


def verified_personal_runtime_context(settings: AppConfig, claims: Mapping[str, object]) -> PersonalRuntimeContext:
    return _personal_runtime_context(personal_identity_policy_from_app_config(settings), claims, settings.mcp.permission_group_claim)


def _personal_runtime_context(policy: PersonalIdentityPolicy, claims: Mapping[str, object], group_claim: str) -> PersonalRuntimeContext:
    resolution = canonical_principal(policy, personal_identity_facts(claims))
    if not isinstance(resolution, ResolvedPersonalIdentity):
        raise PersonalRuntimeUnavailable("Personal identity unavailable")
    groups = personal_group_membership(claims.get(group_claim))
    return PersonalRuntimeContext(principal=resolution.principal, group_ids=groups.group_ids)


class McpPersonalRuntimeContextProvider:
    def __init__(self, settings: AppConfig) -> None:
        self._settings = settings
        self._policy = personal_identity_policy_from_app_config(settings)

    async def get_context(self) -> PersonalRuntimeContext:
        token = get_access_token()
        if token is None or not isinstance(token.claims, Mapping):
            raise PersonalRuntimeUnavailable("Personal identity unavailable")
        return _personal_runtime_context(
            self._policy,
            authenticated_personal_mcp_claims(self._settings, self._policy, token.claims),
            self._settings.mcp.permission_group_claim,
        )


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
