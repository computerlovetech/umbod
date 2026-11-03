import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, AuthContext
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from tests.umbod.mcp.test_personal_caller import _settings
from umbod.core.callers import AuthenticationProvenance, UnavailableSubject
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalCallerProvider
from umbod.mcp.connectors.downstream_mcp import personal_runtime
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalCaller, UnavailablePersonalCaller
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalCallerProvider, personal_tool_permission_check


@pytest.mark.asyncio
async def test_runtime_context_reads_each_current_verified_token_and_groups() -> None:
    settings = _settings().model_copy(update={"mcp": _settings().mcp.model_copy(update={"permission_group_claim": "groups"})})
    provider = McpPersonalCallerProvider(settings)
    for subject, groups in (("alice", ["team", "team", "", " "]), ("bob", "second")):
        token = AccessToken(token="outer-token", client_id="client", scopes=[], claims={"sub": subject, "groups": groups})
        marker = auth_context_var.set(AuthenticatedUser(token))
        try:
            context = await provider.get_caller()
            assert isinstance(context, PersonalCaller)
            assert context.caller.authentication == AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
            assert context.principal.subject == subject
            assert context.principal.namespace == "authority"
            assert context.groups.group_ids == (("team",) if subject == "alice" else ("second",))
        finally:
            auth_context_var.reset(marker)
    assert isinstance(await provider.get_caller(), UnavailablePersonalCaller)


@pytest.mark.asyncio
@pytest.mark.parametrize("claims", ({}, {"sub": "machine", "grant_type": "client_credentials"}, {"sub": "alice", "iss": "https://foreign/"}))
async def test_bad_verified_identity_never_downgrades_to_shared(claims: dict[str, object]) -> None:
    provider = McpPersonalCallerProvider(_settings())
    marker = auth_context_var.set(AuthenticatedUser(AccessToken(token="opaque", client_id="client", scopes=[], claims=claims)))
    try:
        assert isinstance(await provider.get_caller(), UnavailablePersonalCaller)
    finally:
        auth_context_var.reset(marker)


@pytest.mark.asyncio
async def test_untrusted_metadata_cannot_select_authoritative_personal_dispatch() -> None:
    server = FastMCP("test")

    @server.tool(meta={"personal": True, "personal_runtime": True, "connector_id": "personal", "operation_name": "read"})
    async def impostor() -> str:
        return "never"

    tool = await server.get_tool("impostor")
    assert not await personal_tool_permission_check(lambda context: False)(AuthContext(token=None, component=tool))
    assert await personal_tool_permission_check(lambda context: True)(AuthContext(token=None, component=tool))


@pytest.mark.asyncio
async def test_capture_reads_one_token_and_keeps_entra_owner_without_raw_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    token = AccessToken(token="opaque", client_id="client", scopes=[], claims={"oid": "object", "tid": "tenant", "scp": "access", "iss": "https://upstream/"})
    reader = Mock(return_value=token)
    monkeypatch.setattr(personal_runtime, "get_access_token", reader)
    monkeypatch.setattr(personal_runtime, "get_server", lambda: SimpleNamespace(auth=object()))
    provider: PersonalCallerProvider = McpPersonalCallerProvider(_settings("azure_entra_id"))
    captured = await provider.get_caller()
    assert isinstance(captured, PersonalCaller)
    assert isinstance(captured.caller.subject, UnavailableSubject)
    assert captured.caller.authentication == AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
    assert captured.principal.subject == "tenant:object"
    reader.assert_called_once_with()


@pytest.mark.asyncio
async def test_overlapping_captures_are_caller_local() -> None:
    provider: PersonalCallerProvider = McpPersonalCallerProvider(_settings())

    async def capture(subject: str) -> PersonalCaller:
        token = AccessToken(token="opaque", client_id="client", scopes=[], claims={"sub": subject, "groups": [subject]})
        marker = auth_context_var.set(AuthenticatedUser(token))
        try:
            await asyncio.sleep(0)
            captured = await provider.get_caller()
            assert isinstance(captured, PersonalCaller)
            return captured
        finally:
            auth_context_var.reset(marker)

    first, second = await asyncio.gather(capture("alice"), capture("bob"))
    assert first.principal.subject == "alice"
    assert second.principal.subject == "bob"
    assert first.groups.group_ids == ("alice",)
    assert second.groups.group_ids == ("bob",)
