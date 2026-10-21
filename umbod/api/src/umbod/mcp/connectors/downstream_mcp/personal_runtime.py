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
from umbod.core.connectors.downstream_mcp.personal_connections.principal import canonical_principal
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.core.connectors.downstream_mcp.personal_tools import PersonalRuntimeContext

from .tool_invocation import AuthorizedPersonalTool


def verified_personal_runtime_context(settings: AppConfig, claims: Mapping[str, object]) -> PersonalRuntimeContext:
    principal = canonical_principal(settings, claims)
    if principal is None:
        raise PersonalRuntimeUnavailable("Personal identity unavailable")
    value = claims.get(settings.mcp.permission_group_claim)
    if isinstance(value, str):
        groups = (value,) if value.strip() else ()
    elif isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        groups = tuple(item for item in value if item.strip())
    else:
        groups = ()
    return PersonalRuntimeContext(principal=principal, group_ids=tuple(sorted(set(groups))))


class McpPersonalRuntimeContextProvider:
    def __init__(self, settings: AppConfig) -> None:
        self._settings = settings

    async def get_context(self) -> PersonalRuntimeContext:
        token = get_access_token()
        if token is None or not isinstance(token.claims, Mapping):
            raise PersonalRuntimeUnavailable("Personal identity unavailable")
        return verified_personal_runtime_context(self._settings, token.claims)


class PersonalToolNameClaims(Protocol):
    async def personal_tool_name_claims(self) -> tuple[str, ...]: ...


class PersonalToolReservationMiddleware(Middleware):
    def __init__(self, claims: PersonalToolNameClaims) -> None:
        self._claims = claims

    async def _allows(self, tool: Tool, reserved: tuple[str, ...]) -> bool:
        if isinstance(tool, AuthorizedPersonalTool):
            return tool.name in reserved and await tool.is_authorized()
        return tool.name not in reserved

    async def on_list_tools(self, context: MiddlewareContext[mt.ListToolsRequest], call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]]) -> Sequence[Tool]:
        reserved = await self._claims.personal_tool_name_claims()
        tools = await call_next(context)
        authorized: list[Tool] = []
        for tool in tools:
            if not await self._allows(tool, reserved):
                continue
            if tool.name in reserved:
                runtime = context.fastmcp_context
                if runtime is None:
                    continue
                resolved = await runtime.fastmcp.get_tool(tool.name, version=_requested_version({"fastmcp": {"version": tool.version}}))
                if resolved is None or not await self._allows(resolved, reserved):
                    continue
            authorized.append(tool)
        return authorized

    async def on_call_tool(self, context: MiddlewareContext[mt.CallToolRequestParams], call_next: CallNext[mt.CallToolRequestParams, ToolResult]) -> ToolResult:
        reserved = await self._claims.personal_tool_name_claims()
        if context.message.name not in reserved:
            return await call_next(context)
        runtime = context.fastmcp_context
        if runtime is None:
            raise ToolError("Tool is not available")
        tool = await runtime.fastmcp.get_tool(context.message.name, version=_requested_version(context.message.meta))
        if tool is None or not await self._allows(tool, reserved):
            raise ToolError("Tool is not available")
        return await call_next(context)


def personal_tool_permission_check(legacy: Callable[[AuthContext], bool]) -> Callable[[AuthContext], Awaitable[bool]]:
    async def check(context: AuthContext) -> bool:
        if isinstance(context.component, AuthorizedPersonalTool):
            return await context.component.is_authorized()
        return legacy(context)
    return check
