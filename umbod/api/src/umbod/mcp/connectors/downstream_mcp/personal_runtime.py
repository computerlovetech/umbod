from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

import mcp.types as mt
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.middleware.authorization import _requested_version
from fastmcp.tools import Tool, ToolResult

from fastmcp.server.auth import AuthContext
from fastmcp.server.dependencies import get_access_token

from umbod.config.app import AppConfig
from umbod.core.connectors.downstream_mcp.adapters.identity import authenticated_personal_mcp_claims, personal_identity_facts
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
from umbod.core.callers import AuthenticationProvenance, GroupMembership, LegacyGroupClaimPolicy
from umbod.core.callers.groups import resolve_legacy_group_membership
from umbod.core.connectors.downstream_mcp.personal.connections import (
    PersonalCaller,
    PersonalCallerProvider,
    ResolvedPersonalIdentity,
    UnavailablePersonalCaller,
    canonical_principal,
)
from umbod.core.connectors.downstream_mcp.personal.tools import (
    InvokePersonalTool,
    PersonalAuthorizationRequired,
    PersonalInventoryRefreshRequired,
    PersonalMcpTransport,
    PersonalToolAccessStore,
    PersonalToolResult,
    PersonalToolRuntimeService,
)
from umbod.mcp.signals.diagnostics import invocation_failure

from .personal_recovery import personal_authorization_failure, personal_inventory_failure, validate_recovery_origin
from umbod.mcp.auth.caller import authentication_provenance, caller_context_from_access_token
from umbod.mcp.auth.membership import verified_mcp_caller

from .namespaces import PersonalToolNameMatcher, PersonalToolNamespace
from .tool_invocation import AuthorizedPersonalTool


class McpPersonalCallerProvider:
    def __init__(self, settings: AppConfig, server: FastMCP) -> None:
        self._settings = settings
        self._server = server
        self._policy = personal_identity_policy_from_app_config(settings)

    async def get_caller(self) -> PersonalCaller | UnavailablePersonalCaller:
        token = get_access_token()
        authentication = authentication_provenance(self._server.auth)
        if authentication is AuthenticationProvenance.UNAVAILABLE or token is None or not isinstance(token.claims, Mapping):
            return UnavailablePersonalCaller(kind="unavailable")
        claims = authenticated_personal_mcp_claims(self._settings, self._policy, token.claims)
        resolution = canonical_principal(self._policy, personal_identity_facts(claims))
        if not isinstance(resolution, ResolvedPersonalIdentity):
            return UnavailablePersonalCaller(kind="unavailable")
        if authentication is AuthenticationProvenance.UPSTREAM_VERIFIED:
            snapshot = verified_mcp_caller(self._server, token)
            if snapshot is not None:
                return PersonalCaller(caller=snapshot.caller, principal=resolution.principal, groups=snapshot.groups)
            groups = GroupMembership(group_ids=())
        else:
            groups = resolve_legacy_group_membership(
                claims, (self._settings.mcp.permission_group_claim,), LegacyGroupClaimPolicy.PERSONAL,
            )
        caller = caller_context_from_access_token(token, authentication)
        return PersonalCaller(caller=caller, principal=resolution.principal, groups=groups)


class McpPersonalToolRuntime:
    def __init__(
        self,
        callers: PersonalCallerProvider,
        access: PersonalToolAccessStore,
        transport: PersonalMcpTransport,
        clock: Callable[[], datetime],
        recovery_origin: str,
    ) -> None:
        self._recovery_origin = validate_recovery_origin(recovery_origin)
        self._callers = callers
        self._access = access
        self._transport = transport
        self._clock = clock

    async def _operation(self) -> PersonalToolRuntimeService:
        caller = await self._callers.get_caller()
        return PersonalToolRuntimeService(caller, self._access, self._transport, self._clock)

    async def execute(self, command: InvokePersonalTool) -> PersonalToolResult:
        operation = await self._operation()
        try:
            return await operation.execute(command)
        except PersonalAuthorizationRequired as error:
            invocation_failure.set(error.diagnostic)
            return personal_authorization_failure(self._recovery_origin, command.identity.connector_id, error)
        except PersonalInventoryRefreshRequired as error:
            invocation_failure.set(error.diagnostic)
            return personal_inventory_failure(self._recovery_origin, command.identity.connector_id)


class PersonalDiscoveryMiddleware(Middleware):
    def __init__(self, claims: PersonalToolNamespace) -> None:
        self._claims = claims

    async def on_message(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        async with self._claims.discovery_operation():
            return await call_next(context)


class PersonalToolReservationMiddleware(Middleware):
    def __init__(self, claims: PersonalToolNamespace) -> None:
        self._claims = claims

    async def _allows(self, tool: Tool, namespace: PersonalToolNameMatcher) -> bool:
        reserved = namespace.is_personal_tool_name(tool.name)
        if isinstance(tool, AuthorizedPersonalTool):
            return reserved and await tool.is_authorized()
        return not reserved

    async def on_list_tools(self, context: MiddlewareContext[mt.ListToolsRequest], call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]]) -> Sequence[Tool]:
        async with self._claims.discovery_operation():
            return await self._list_tools(context, call_next)

    async def _list_tools(self, context: MiddlewareContext[mt.ListToolsRequest], call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]]) -> Sequence[Tool]:
        tools = await call_next(context)
        namespace = await self._claims.capture_personal_tool_namespace()
        authorized: list[Tool] = []
        for tool in tools:
            if not await self._allows(tool, namespace):
                continue
            if namespace.is_personal_tool_name(tool.name):
                runtime = context.fastmcp_context
                if runtime is None:
                    continue
                resolved = await runtime.fastmcp.get_tool(tool.name, version=_requested_version({"fastmcp": {"version": tool.version}}))
                if not isinstance(resolved, AuthorizedPersonalTool) or not isinstance(tool, AuthorizedPersonalTool) or not tool.same_discovery_identity(resolved) or not await self._allows(resolved, namespace):
                    continue
            authorized.append(tool)
        return authorized

    async def on_call_tool(self, context: MiddlewareContext[mt.CallToolRequestParams], call_next: CallNext[mt.CallToolRequestParams, ToolResult]) -> ToolResult:
        async with self._claims.discovery_operation():
            return await self._call_tool(context, call_next)

    async def _call_tool(self, context: MiddlewareContext[mt.CallToolRequestParams], call_next: CallNext[mt.CallToolRequestParams, ToolResult]) -> ToolResult:
        namespace = await self._claims.capture_personal_tool_namespace()
        if not namespace.is_personal_tool_name(context.message.name):
            return await call_next(context)
        runtime = context.fastmcp_context
        if runtime is None:
            raise ToolError("Tool is not available")
        tool = await runtime.fastmcp.get_tool(context.message.name, version=_requested_version(context.message.meta))
        if tool is None or not await self._allows(tool, namespace):
            raise ToolError("Tool is not available")
        return await call_next(context)


def personal_tool_permission_check(legacy: Callable[[AuthContext], bool]) -> Callable[[AuthContext], Awaitable[bool]]:
    async def check(context: AuthContext) -> bool:
        if isinstance(context.component, AuthorizedPersonalTool):
            return await context.component.is_authorized()
        return legacy(context)
    return check
