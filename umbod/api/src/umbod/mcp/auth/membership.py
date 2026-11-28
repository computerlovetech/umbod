from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from typing import Any, Protocol

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from umbod.core.callers import AuthenticationProvenance, GroupMembership, LegacyGroupClaimPolicy
from umbod.core.callers.membership import (
    GroupMembershipResolution,
    GroupMembershipResolver,
    INHERITED_GROUP_MEMBERSHIP,
    UNAVAILABLE_GROUP_MEMBERSHIP,
)


class GroupMembershipSnapshotSource(Protocol):
    async def capture(self) -> GroupMembershipResolver: ...


class McpGroupMembership(Middleware):
    def __init__(
        self, source: GroupMembershipSnapshotSource, authentication: AuthenticationProvenance,
    ) -> None:
        self._source = source
        self._authentication = authentication
        self._snapshot: ContextVar[GroupMembershipResolver] = ContextVar(
            "mcp_group_membership", default=UNAVAILABLE_GROUP_MEMBERSHIP,
        )

    async def on_message(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        snapshot = INHERITED_GROUP_MEMBERSHIP
        if self._authentication is AuthenticationProvenance.UPSTREAM_VERIFIED and get_access_token() is not None:
            snapshot = await self._source.capture()
        token = self._snapshot.set(snapshot)
        try:
            return await call_next(context)
        finally:
            self._snapshot.reset(token)

    def resolve(
        self, claims: Mapping[str, object], claim_fields: Sequence[str],
        policy: LegacyGroupClaimPolicy, authentication: AuthenticationProvenance,
    ) -> GroupMembership:
        return self._snapshot.get().resolve(claims, claim_fields, policy, authentication)


def server_group_membership_resolver(server: FastMCP) -> GroupMembershipResolution:
    return getattr(server, "group_membership_resolver", INHERITED_GROUP_MEMBERSHIP)
