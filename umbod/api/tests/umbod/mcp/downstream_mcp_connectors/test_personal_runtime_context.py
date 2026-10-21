import pytest
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, AuthContext
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from tests.umbod.mcp.test_personal_canonical_principal import _settings
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeUnavailable
from umbod.mcp.downstream_mcp_connectors.personal_runtime import McpPersonalRuntimeContextProvider, personal_tool_permission_check


@pytest.mark.asyncio
async def test_runtime_context_reads_each_current_verified_token_and_groups() -> None:
    settings = _settings().model_copy(update={"mcp": _settings().mcp.model_copy(update={"permission_group_claim": "groups"})})
    provider = McpPersonalRuntimeContextProvider(settings)
    for subject, groups in (("alice", ["team", "team", "", " "]), ("bob", "second")):
        token = AccessToken(token="outer-token", client_id="client", scopes=[], claims={"sub": subject, "groups": groups})
        marker = auth_context_var.set(AuthenticatedUser(token))
        try:
            context = await provider.get_context()
            assert context.principal.subject == subject
            assert context.principal.namespace == "authority"
            assert context.group_ids == (("team",) if subject == "alice" else ("second",))
        finally:
            auth_context_var.reset(marker)
    with pytest.raises(PersonalRuntimeUnavailable):
        await provider.get_context()


@pytest.mark.asyncio
@pytest.mark.parametrize("claims", ({}, {"sub": "machine", "grant_type": "client_credentials"}, {"sub": "alice", "iss": "https://foreign/"}))
async def test_bad_verified_identity_never_downgrades_to_shared(claims: dict[str, object]) -> None:
    provider = McpPersonalRuntimeContextProvider(_settings())
    marker = auth_context_var.set(AuthenticatedUser(AccessToken(token="opaque", client_id="client", scopes=[], claims=claims)))
    try:
        with pytest.raises(PersonalRuntimeUnavailable):
            await provider.get_context()
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
