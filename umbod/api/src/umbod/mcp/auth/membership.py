from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Protocol

from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import fastmcp_request_ctx, get_access_token, get_context
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from umbod.core.callers import AuthenticationProvenance, CallerSnapshot, GroupMembership, LegacyGroupClaimPolicy
from umbod.core.callers.groups import resolve_legacy_group_membership
from umbod.core.callers.membership import GroupMembershipResolver
from umbod.core.groups import GroupInstance
from umbod.core.permissions.domain import GroupPermissionSet
from umbod.core.permissions.ports import GroupInstancePermissionReader
from umbod.mcp.auth.agent_tokens import PublicAgentMultiAuth, is_agent_access_token, verified_agent_identity
from umbod.mcp.auth.caller import authentication_provenance_for_token, caller_context_from_access_token


_EMPTY_AGENT_GRANTS = GroupPermissionSet(group_id="", connector_ids=(), capabilities=())
_AGENT_PROTOCOL_METHODS = frozenset({"initialize", "server/discover", "ping"})
_AGENT_NOTIFICATIONS = frozenset({"notifications/initialized", "notifications/cancelled"})
_AGENT_CAPABILITY_METHODS = frozenset({
    "tools/list", "tools/call", "prompts/list", "prompts/get", "resources/list",
    "resources/templates/list", "resources/read",
})


class GroupMembershipRulesSource(Protocol):
    async def capture(self) -> GroupMembershipResolver: ...


class McpAccessTokenAvailability(Enum):
    UNAVAILABLE = auto()


@dataclass
class _VerifiedMessageCaller:
    wire_message: object
    access_token: AccessToken = field(repr=False)
    snapshot: CallerSnapshot | GroupPermissionSet
    active: bool


def _wire_message() -> object:
    context = fastmcp_request_ctx.get()
    return context._srctx if context is not None and context.session is not None else None


def _is_foreground_operation(server: FastMCP) -> bool:
    try:
        context = get_context()
    except RuntimeError:
        return False
    return context.fastmcp is server and not context.is_background_task


class McpCallerSnapshotMiddleware(Middleware):
    def __init__(
        self, server: FastMCP, source: GroupMembershipRulesSource,
        instance_permissions: GroupInstancePermissionReader,
    ) -> None:
        self._server = server
        self._source = source
        self._instance_permissions = instance_permissions
        self._caller: ContextVar[_VerifiedMessageCaller] = ContextVar("mcp_verified_message_caller")

    async def on_message(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        access_token = get_access_token()
        if access_token is None or not _is_foreground_operation(self._server):
            return await call_next(context)
        wire_message = _wire_message()
        if self.current(access_token) is not None:
            return await call_next(context)
        if is_agent_access_token(self._server.auth, access_token):
            if context.type == "notification":
                return await call_next(context) if context.method in _AGENT_NOTIFICATIONS else None
            if context.method in _AGENT_PROTOCOL_METHODS:
                return await call_next(context)
            if context.method not in _AGENT_CAPABILITY_METHODS or getattr(context.message, "task", None) is not None:
                raise AuthorizationError("MCP request is unavailable to agent credentials")
            if wire_message is None:
                raise AuthorizationError("MCP request authorization is unavailable")
            snapshot = await self._read_agent_grants(access_token)
        elif authentication_provenance_for_token(self._server.auth, access_token) is AuthenticationProvenance.UPSTREAM_VERIFIED:
            rules = await self._source.capture()
            snapshot = CallerSnapshot(
                caller=caller_context_from_access_token(access_token, AuthenticationProvenance.UPSTREAM_VERIFIED),
                groups=rules.resolve_verified(access_token.claims),
            )
        else:
            return await call_next(context)
        caller = _VerifiedMessageCaller(wire_message, access_token, snapshot, active=True)
        binding = self._caller.set(caller)
        try:
            return await call_next(context)
        finally:
            caller.active = False
            self._caller.reset(binding)

    async def _read_agent_grants(self, access_token: AccessToken) -> GroupPermissionSet:
        identity = verified_agent_identity(self._server.auth, access_token)
        if identity is None:
            return _EMPTY_AGENT_GRANTS
        group = GroupInstance(group_id=identity.group_id, instance_id=identity.group_instance_id)
        try:
            grants = await self._instance_permissions.read_for_group_instance(group)
        except Exception:
            raise AuthorizationError("Agent capability permissions are unavailable") from None
        return grants if grants.group_id == group.group_id else _EMPTY_AGENT_GRANTS

    def current(self, access_token: AccessToken) -> CallerSnapshot | GroupPermissionSet | None:
        caller = self._caller.get(None)
        if (
            caller is not None
            and caller.active
            and caller.wire_message is _wire_message()
            and caller.access_token is access_token
            and _is_foreground_operation(self._server)
        ):
            return caller.snapshot
        return None


def _current_snapshot(server: FastMCP, access_token: AccessToken) -> CallerSnapshot | GroupPermissionSet | None:
    middleware: McpCallerSnapshotMiddleware | None = getattr(server, "caller_snapshot_middleware", None)
    if middleware is None:
        return None
    return middleware.current(access_token)


def verified_mcp_caller(server: FastMCP, access_token: AccessToken) -> CallerSnapshot | None:
    snapshot = _current_snapshot(server, access_token)
    return snapshot if isinstance(snapshot, CallerSnapshot) else None


def restricted_mcp_grants(
    server: FastMCP, access_token: AccessToken | McpAccessTokenAvailability,
) -> GroupPermissionSet | None:
    if not isinstance(server.auth, PublicAgentMultiAuth):
        return None
    if access_token is McpAccessTokenAvailability.UNAVAILABLE:
        return _EMPTY_AGENT_GRANTS
    if not is_agent_access_token(server.auth, access_token):
        provenance = authentication_provenance_for_token(server.auth, access_token)
        return _EMPTY_AGENT_GRANTS if provenance is AuthenticationProvenance.UNAVAILABLE else None
    snapshot = _current_snapshot(server, access_token)
    return snapshot if isinstance(snapshot, GroupPermissionSet) else _EMPTY_AGENT_GRANTS


def capture_mcp_caller(
    server: FastMCP, access_token: AccessToken | McpAccessTokenAvailability,
    claim_fields: Sequence[str], policy: LegacyGroupClaimPolicy,
) -> CallerSnapshot:
    if access_token is McpAccessTokenAvailability.UNAVAILABLE:
        return CallerSnapshot(
            caller=caller_context_from_access_token(None, AuthenticationProvenance.UNAVAILABLE),
            groups=GroupMembership(group_ids=()),
        )
    authentication = authentication_provenance_for_token(server.auth, access_token)
    if authentication is AuthenticationProvenance.UPSTREAM_VERIFIED:
        snapshot = verified_mcp_caller(server, access_token)
        if snapshot is not None:
            if server.permission_group_claim in claim_fields:
                return snapshot
            return CallerSnapshot(caller=snapshot.caller, groups=GroupMembership(group_ids=()))
        groups = GroupMembership(group_ids=())
    elif authentication in {AuthenticationProvenance.AGENT_CREDENTIAL, AuthenticationProvenance.UNAVAILABLE}:
        groups = GroupMembership(group_ids=())
    else:
        observed_claims = getattr(access_token, "claims", {})
        claims = observed_claims if isinstance(observed_claims, Mapping) else {}
        groups = resolve_legacy_group_membership(claims, claim_fields, policy)
    return CallerSnapshot(caller=caller_context_from_access_token(access_token, authentication), groups=groups)
