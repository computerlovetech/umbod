from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

import pytest
from fastmcp import FastMCP
from fastmcp.server.context import Context

from umbod.mcp.logging.audit.event import McpAnonymousAuditActor, McpAuthenticatedAuditActor
from umbod.mcp.logging.audit.identity import McpAuditIdentityAdapter


class _FakeSession:
    _fastmcp_state_prefix = "session-1"


@dataclass(frozen=True)
class _Token:
    claims: object
    client_id: object = None


@dataclass(frozen=True)
class _RequestContext:
    request_id: object


@dataclass(frozen=True)
class _Context:
    session_id: object = None
    request_context: object = None


def test_request_without_token_is_anonymous(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("umbod.mcp.logging.audit.identity.get_access_token", lambda: None)

    identity = McpAuditIdentityAdapter().identity_from_request(None)

    assert isinstance(identity.actor, McpAnonymousAuditActor)
    assert identity.client.attributes == {}


@pytest.mark.parametrize("claims", [None, "invalid", ["invalid"]])
def test_malformed_claims_are_anonymous(monkeypatch: pytest.MonkeyPatch, claims: object) -> None:
    monkeypatch.setattr(
        "umbod.mcp.logging.audit.identity.get_access_token", lambda: _Token(claims)
    )

    identity = McpAuditIdentityAdapter().identity_from_request(None)

    assert isinstance(identity.actor, McpAnonymousAuditActor)


def test_user_identity_claim_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    token = _Token(
        claims={"sub": "subject", "email": "email", "preferred_username": "username"},
        client_id="client",
    )
    monkeypatch.setattr("umbod.mcp.logging.audit.identity.get_access_token", lambda: token)

    identity = McpAuditIdentityAdapter().identity_from_request(None)

    assert identity.actor == McpAuthenticatedAuditActor("subject")


def test_client_metadata_filters_invalid_values_and_converts_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _Token(claims={"client_name": "agent", "ignored": "value"}, client_id=42)
    context = _Context(session_id=9, request_context=_RequestContext(request_id=123))
    monkeypatch.setattr("umbod.mcp.logging.audit.identity.get_access_token", lambda: token)

    identity = McpAuditIdentityAdapter().identity_from_request(context)

    assert identity.client.attributes == {"client_name": "agent", "request_id": "123"}


def test_invocation_actor_uses_one_consistent_token_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def access_token() -> _Token:
        nonlocal calls
        calls += 1
        return _Token(claims={"email": "person@example.com"}, client_id="agent-client")

    token_provider: Callable[[], _Token] = access_token
    monkeypatch.setattr("umbod.mcp.logging.audit.identity.get_access_token", token_provider)

    actor = McpAuditIdentityAdapter().invocation_actor(_Context(session_id="session"))

    assert calls == 1
    assert actor.authenticated_user_id == "person@example.com"
    assert actor.agent_client_id == "agent-client"
    assert actor.session_id == "session"


def test_identity_from_request_handles_missing_fastmcp_request_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = FastMCP("test")
    adapter = McpAuditIdentityAdapter()
    monkeypatch.setattr("umbod.mcp.logging.audit.identity.get_access_token", lambda: None)

    async def exercise() -> None:
        async with Context(fastmcp=mcp, session=_FakeSession()) as context:
            identity = adapter.identity_from_request(context)
            assert identity.client.request_id is None
            assert identity.client.session_id == "session-1"

    asyncio.run(exercise())
