import jwt
from fastmcp.server.auth.auth import AccessToken

from umbod.config import load_app_config_without_env_file
from umbod.mcp.auth.factory import MCPAuthProviderFactory
from umbod.mcp.settings import MCPAppSettings, MCPSettings


def test_single_test_user_token_claims_come_from_configured_jwt() -> None:
    test_token = _test_jwt({"email": "test-user@example.com", "groups": ["test"]})
    settings = MCPAppSettings(
        mcp=MCPSettings(
            auth_mode="single_test_user",
            test_bearer_token=test_token,
            _env_file=None,
        ),
        _env_file=None,
    )

    provider = MCPAuthProviderFactory().create(settings)
    access_token = provider.access_tokens[test_token]

    assert isinstance(access_token, AccessToken)
    assert access_token.claims == {"email": "test-user@example.com", "groups": ["test"]}


def test_mcp_settings_load_permission_claim_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("UMBOD_MCP_PERMISSION_CLAIM", "roles")

    settings = load_app_config_without_env_file()

    assert settings.mcp.permission_group_claim == "roles"


def _test_jwt(claims: dict[str, object]) -> str:
    return jwt.encode(claims, key="", algorithm="none")
