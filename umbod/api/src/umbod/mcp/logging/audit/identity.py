from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import AuthenticationProvenance, CallerContext, SubjectIdentity
from umbod.core.usage.models import UsageOwnership
from umbod.mcp.auth.agent_tokens import effective_oauth_provider, verified_agent_identity
from umbod.mcp.auth.caller import authentication_provenance_for_token, caller_context_from_access_token
from umbod.mcp.logging.audit.event import (
    McpAnonymousAuditActor,
    McpAuditActorState,
    McpAuditClientMetadata,
    McpAuthenticatedAuditActor,
)
from umbod.mcp.signals.events import McpInvocationActor
from umbod.mcp.usage.identity import resolve_mcp_usage_owner

_USER_ID_FALLBACK_FIELDS = ("email", "preferred_username")


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
    caller: CallerContext
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
        snapshot = _request_identity_snapshot(fastmcp_context)
        return McpAuditIdentity(actor=snapshot.actor, client=snapshot.client)

    def invocation_actor(self, fastmcp_context: object) -> McpInvocationActor:
        return _request_identity_snapshot(fastmcp_context).invocation_actor


def _request_identity_snapshot(fastmcp_context: object) -> _RequestIdentitySnapshot:
    server = getattr(fastmcp_context, "fastmcp", None)
    provider = getattr(server, "auth", None)
    token = get_access_token()
    oauth_provider = effective_oauth_provider(provider, token)
    snapshot = _access_token_snapshot(provider, token, oauth_provider)
    configured_issuer = getattr(server, 'usage_identity_issuer', '')
    return _normalize_request_identity(
        snapshot, _framework_context_snapshot(fastmcp_context),
        resolve_mcp_usage_owner(
            snapshot.caller, oauth_provider,
            configured_issuer if isinstance(configured_issuer, str) else '',
        ),
    )


def _normalize_request_identity(
    token: _AccessTokenSnapshot,
    context: _FrameworkContextSnapshot,
    usage_owner: UsageOwnership,
) -> _RequestIdentitySnapshot:
    identity = _user_identity(token.caller, token.claims)
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
            usage_owner=usage_owner,
        ),
    )


def _audit_actor(identity: _UserIdentity) -> McpAuditActorState:
    if isinstance(identity, _AnonymousUserIdentity):
        return McpAnonymousAuditActor()
    return McpAuthenticatedAuditActor(identity.user_id)


def _present_metadata(**values: str | None) -> Mapping[str, str]:
    return {key: value for key, value in values.items() if value is not None}


def _access_token_snapshot(
    provider: object, token: object, oauth_provider: object,
) -> _AccessTokenSnapshot:
    authentication = authentication_provenance_for_token(provider, token)
    caller = caller_context_from_access_token(token, authentication)
    if authentication in {AuthenticationProvenance.AGENT_CREDENTIAL, AuthenticationProvenance.UNAVAILABLE}:
        identity = verified_agent_identity(provider, token)
        return _AccessTokenSnapshot(caller, {}, identity.agent_id if identity is not None else None)
    claims = getattr(token, "claims", None)
    client_field = "original_client_id" if oauth_provider is not provider else "client_id"
    client_id = getattr(token, client_field, None)
    return _AccessTokenSnapshot(
        caller=caller,
        claims=claims if isinstance(claims, Mapping) else {},
        client_id=client_id if isinstance(client_id, str) else None,
    )


def _user_identity(caller: CallerContext, claims: Mapping[str, object]) -> _UserIdentity:
    if isinstance(caller.subject, SubjectIdentity) and caller.subject.subject:
        return _AuthenticatedUserIdentity(caller.subject.subject)
    for field in _USER_ID_FALLBACK_FIELDS:
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
