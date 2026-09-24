from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from fastmcp.server.dependencies import get_access_token

from umbod.mcp.logging.audit.event import (
    McpAnonymousAuditActor,
    McpAuditActorState,
    McpAuditClientMetadata,
    McpAuthenticatedAuditActor,
)
from umbod.mcp.logging.invocation.event import McpInvocationActor

_USER_ID_CLAIM_FIELDS = ("sub", "email", "preferred_username")


@dataclass(frozen=True)
class McpAuditIdentity:
    actor: McpAuditActorState
    client: McpAuditClientMetadata


@dataclass(frozen=True)
class _RequestIdentitySnapshot:
    actor: McpAuditActorState
    client: McpAuditClientMetadata
    invocation_actor: McpInvocationActor


@dataclass(frozen=True)
class _AccessTokenSnapshot:
    claims: Mapping[str, object]
    client_id: str | None


@dataclass(frozen=True)
class _FrameworkContextSnapshot:
    session_id: str | None
    request_id: str | None


@dataclass(frozen=True)
class _AnonymousUserIdentity:
    pass


@dataclass(frozen=True)
class _AuthenticatedUserIdentity:
    user_id: str


_UserIdentity = _AnonymousUserIdentity | _AuthenticatedUserIdentity


class McpAuditIdentitySource(Protocol):
    def identity_from_request(self, fastmcp_context: object) -> McpAuditIdentity: ...

    def invocation_actor(self, fastmcp_context: object) -> McpInvocationActor: ...


def audit_identity_from_invocation_actor(actor: McpInvocationActor) -> McpAuditIdentity:
    identity: _UserIdentity = (
        _AuthenticatedUserIdentity(actor.authenticated_user_id)
        if actor.authenticated_user_id is not None
        else _AnonymousUserIdentity()
    )
    return McpAuditIdentity(
        actor=_audit_actor(identity),
        client=McpAuditClientMetadata(
            _present_metadata(client_id=actor.agent_client_id, session_id=actor.session_id)
        ),
    )


class McpAuditIdentityAdapter:
    def identity_from_request(self, fastmcp_context: object) -> McpAuditIdentity:
        snapshot = _normalize_request_identity(
            _access_token_snapshot(get_access_token()),
            _framework_context_snapshot(fastmcp_context),
        )
        return McpAuditIdentity(actor=snapshot.actor, client=snapshot.client)

    def invocation_actor(self, fastmcp_context: object) -> McpInvocationActor:
        return _normalize_request_identity(
            _access_token_snapshot(get_access_token()),
            _framework_context_snapshot(fastmcp_context),
        ).invocation_actor


def _normalize_request_identity(
    token: _AccessTokenSnapshot,
    context: _FrameworkContextSnapshot,
) -> _RequestIdentitySnapshot:
    identity = _user_identity(token.claims)
    user_id = identity.user_id if isinstance(identity, _AuthenticatedUserIdentity) else None
    return _RequestIdentitySnapshot(
        actor=_audit_actor(identity),
        client=McpAuditClientMetadata(
            _present_metadata(
                client_id=token.client_id,
                client_name=_client_name(token.claims),
                session_id=context.session_id,
                request_id=context.request_id,
            )
        ),
        invocation_actor=McpInvocationActor(
            authenticated_user_id=user_id,
            agent_client_id=token.client_id,
            session_id=context.session_id,
        ),
    )


def _audit_actor(identity: _UserIdentity) -> McpAuditActorState:
    if isinstance(identity, _AnonymousUserIdentity):
        return McpAnonymousAuditActor()
    return McpAuthenticatedAuditActor(identity.user_id)


def _present_metadata(**values: str | None) -> Mapping[str, str]:
    return {key: value for key, value in values.items() if value is not None}


def _access_token_snapshot(token: object) -> _AccessTokenSnapshot:
    claims = getattr(token, "claims", None)
    client_id = getattr(token, "client_id", None)
    return _AccessTokenSnapshot(
        claims=claims if isinstance(claims, Mapping) else {},
        client_id=client_id if isinstance(client_id, str) else None,
    )


def _user_identity(claims: Mapping[str, object]) -> _UserIdentity:
    for field in _USER_ID_CLAIM_FIELDS:
        value = claims.get(field)
        if isinstance(value, str) and value:
            return _AuthenticatedUserIdentity(value)
    return _AnonymousUserIdentity()


def _client_name(claims: Mapping[str, object]) -> str | None:
    value = claims.get("client_name")
    return value if isinstance(value, str) and value else None


def _framework_context_snapshot(fastmcp_context: object) -> _FrameworkContextSnapshot:
    session_id = getattr(fastmcp_context, "session_id", None)
    request_context = getattr(fastmcp_context, "request_context", None)
    request_id = getattr(request_context, "request_id", None)
    return _FrameworkContextSnapshot(
        session_id=session_id if isinstance(session_id, str) else None,
        request_id=str(request_id) if request_id is not None else None,
    )
