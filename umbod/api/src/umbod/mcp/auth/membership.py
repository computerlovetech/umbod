from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Protocol

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import fastmcp_request_ctx, get_access_token, get_context
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from umbod.core.callers import AuthenticationProvenance, CallerSnapshot, GroupMembership, LegacyGroupClaimPolicy
from umbod.core.callers.groups import resolve_legacy_group_membership
from umbod.core.callers.membership import GroupMembershipResolver
from umbod.mcp.auth.caller import authentication_provenance, caller_context_from_access_token


class GroupMembershipRulesSource(Protocol):
    async def capture(self) -> GroupMembershipResolver: ...


class McpAccessTokenAvailability(Enum):
    UNAVAILABLE = auto()


@dataclass
class _VerifiedMessageCaller:
    wire_message: object
    access_token: str = field(repr=False)
    snapshot: CallerSnapshot
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
    def __init__(self, server: FastMCP, source: GroupMembershipRulesSource) -> None:
        self._server = server
        self._source = source
        self._verified = authentication_provenance(server.auth) is AuthenticationProvenance.UPSTREAM_VERIFIED
        self._caller: ContextVar[_VerifiedMessageCaller] = ContextVar("mcp_verified_message_caller")

    async def on_message(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        if not self._verified or not _is_foreground_operation(self._server):
            return await call_next(context)
        access_token = get_access_token()
        if access_token is None:
            return await call_next(context)
        inherited = self._caller.get(None)
        wire_message = _wire_message()
        if inherited is not None and inherited.wire_message is wire_message:
            return await call_next(context)
        rules = await self._source.capture()
        snapshot = CallerSnapshot(
            caller=caller_context_from_access_token(access_token, AuthenticationProvenance.UPSTREAM_VERIFIED),
            groups=rules.resolve_verified(access_token.claims),
        )
        caller = _VerifiedMessageCaller(wire_message, access_token.token, snapshot, active=True)
        binding = self._caller.set(caller)
        try:
            return await call_next(context)
        finally:
            caller.active = False
            self._caller.reset(binding)

    def current(self, access_token: AccessToken) -> CallerSnapshot | None:
        caller = self._caller.get(None)
        if (
            caller is not None
            and caller.active
            and caller.wire_message is _wire_message()
            and caller.access_token == access_token.token
            and _is_foreground_operation(self._server)
        ):
            return caller.snapshot
        return None


def verified_mcp_caller(server: FastMCP, access_token: AccessToken) -> CallerSnapshot | None:
    middleware: McpCallerSnapshotMiddleware | None = getattr(server, "caller_snapshot_middleware", None)
    if middleware is None:
        return None
    return middleware.current(access_token)


def capture_mcp_caller(
    server: FastMCP, access_token: AccessToken | McpAccessTokenAvailability,
    claim_fields: Sequence[str], policy: LegacyGroupClaimPolicy,
) -> CallerSnapshot:
    if access_token is McpAccessTokenAvailability.UNAVAILABLE:
        return CallerSnapshot(
            caller=caller_context_from_access_token(None, AuthenticationProvenance.UNAVAILABLE),
            groups=GroupMembership(group_ids=()),
        )
    authentication = authentication_provenance(server.auth)
    if authentication is AuthenticationProvenance.UPSTREAM_VERIFIED:
        snapshot = verified_mcp_caller(server, access_token)
        if snapshot is not None:
            if server.permission_group_claim in claim_fields:
                return snapshot
            return CallerSnapshot(caller=snapshot.caller, groups=GroupMembership(group_ids=()))
        groups = GroupMembership(group_ids=())
    else:
        observed_claims = getattr(access_token, "claims", {})
        claims = observed_claims if isinstance(observed_claims, Mapping) else {}
        groups = resolve_legacy_group_membership(claims, claim_fields, policy)
    return CallerSnapshot(caller=caller_context_from_access_token(access_token, authentication), groups=groups)
