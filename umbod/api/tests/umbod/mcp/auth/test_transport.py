from typing import cast

import jwt
import pytest

from umbod.mcp.auth import (
    AuthenticatedMcpTransport,
    UnauthenticatedMcpTransport,
    configured_mcp_transport_authentication,
)
from umbod.mcp.auth.transport import McpTransportAuthentication, fastmcp_authentication_provider
from umbod.mcp.settings import MCPAppSettings, MCPSettings


def test_disabled_authentication_resolves_to_explicit_unauthenticated_transport() -> None:
    settings = MCPAppSettings(mcp=MCPSettings(auth_mode="none", _env_file=None), _env_file=None)

    authentication = configured_mcp_transport_authentication(settings)

    assert isinstance(authentication, UnauthenticatedMcpTransport)
    assert fastmcp_authentication_provider(authentication) is None


@pytest.mark.parametrize("authentication", [None, object()])
def test_invalid_authentication_choice_cannot_silently_disable_authentication(authentication: object) -> None:
    with pytest.raises(TypeError, match="Explicit MCP transport authentication is required"):
        fastmcp_authentication_provider(cast(McpTransportAuthentication, authentication))


@pytest.mark.asyncio
async def test_authenticated_transport_preserves_configured_token_verification() -> None:
    token = jwt.encode({"email": "member@example.test"}, "transport-authentication-test-key-32-bytes", algorithm="HS256")
    settings = MCPAppSettings(
        mcp=MCPSettings(auth_mode="single_test_user", test_bearer_token=token, _env_file=None),
        _env_file=None,
    )

    authentication = configured_mcp_transport_authentication(settings)

    assert isinstance(authentication, AuthenticatedMcpTransport)
    assert fastmcp_authentication_provider(authentication) is authentication.provider
    verified = await authentication.provider.verify_token(token)
    assert verified is not None
    assert verified.claims["email"] == "member@example.test"
    assert await authentication.provider.verify_token("unrecognized-token") is None
