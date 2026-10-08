import json
from pathlib import Path
from unittest.mock import patch

import httpx2
import jwt
import pytest
from httpx import Response
from starlette.testclient import TestClient

from umbod.mcp.auth import MCPAuthProviderFactory
from umbod.mcp.settings import (
    MCPAppSettings,
    MCPSettings,
    OIDCOAuthStorageSettings,
    OIDCSettings,
    PublicEndpointSettings,
)
from tests.umbod.mcp.auth.fake_token_auth import (
    FakeTokenValidator,
    TokenValidatorAuthProvider,
)
from tests.mcp_fixtures import create_test_mcp_http_app

_TEST_OAUTH_STORAGE_ENCRYPTION_KEY = "uVIB4LyODL50BmxXDtJUL-QI1Mdue8HUZbk92i0X8Qc="


@pytest.fixture(autouse=True)
def UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    availability_path = tmp_path / "connectors.json"
    availability_path.write_text(
        json.dumps({"connectors": [{"id": "slack"}, {"id": "test"}]}), encoding="utf-8"
    )
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))


@pytest.mark.parametrize(
    ("provider", "token", "user_email"),
    [
        ("google", "google-valid-token", "alex@example.com"),
        ("azure_entra_id", "azure-valid-token", "alex@contoso.com"),
        ("auth0", "auth0-valid-token", "alex@example.com"),
    ],
)
def test_agent_client_with_valid_provider_user_token_can_reach_mcp_tools(
    provider: str,
    token: str,
    user_email: str,
) -> None:
    settings = MCPAppSettings(oidc=OIDCSettings(provider=provider, _env_file=None), _env_file=None)
    auth_provider = _auth_provider_for_tokens(settings, {token: user_email})

    with TestClient(create_test_mcp_http_app(settings, auth_provider=auth_provider)) as client:
        response = _request_mcp_tool_list(client, token)

    assert response.status_code != 401
    assert response.status_code != 403


def test_server_trusts_only_the_configured_provider_for_mcp_tools() -> None:
    settings = MCPAppSettings(oidc=OIDCSettings(provider="auth0", _env_file=None), _env_file=None)
    auth_provider = _auth_provider_for_tokens(settings, {})

    with TestClient(create_test_mcp_http_app(settings, auth_provider=auth_provider)) as client:
        response = _request_mcp_tool_list(client, "google-valid-token")

    assert response.status_code == 401


def test_oauth_authorization_endpoints_are_available_at_root_for_mcp_clients(
    tmp_path: Path,
) -> None:
    settings = MCPAppSettings(
        mcp=MCPSettings(auth_mode="oidc", _env_file=None),
        oidc=OIDCSettings(
            provider="google",
            client_id="google-client-id",
            client_secret="google-client-secret",
            _env_file=None,
        ),
        oauth_storage=OIDCOAuthStorageSettings(
            directory=str(tmp_path / "fastmcp-oauth"),
            encryption_key=_TEST_OAUTH_STORAGE_ENCRYPTION_KEY,
            _env_file=None,
        ),
        _env_file=None,
    )

    with TestClient(create_test_mcp_http_app(settings)) as client:
        registration_response = client.post("/register", json={})
        authorization_metadata_response = client.get("/.well-known/oauth-authorization-server")

    assert registration_response.status_code != 404
    assert authorization_metadata_response.status_code == 200


@pytest.mark.parametrize(
    ("provider", "upstream_issuer"),
    [
        ("google", "https://accounts.google.com"),
        ("azure_entra_id", "https://login.microsoftonline.com/test-tenant/v2.0"),
        ("auth0", "https://computerlove.eu.auth0.com/"),
    ],
)
def test_oauth_metadata_uses_public_mcp_issuer_without_changing_upstream_issuer(
    provider: str,
    upstream_issuer: str,
    tmp_path: Path,
) -> None:
    public_origin = "https://umbod.computerlove.tech"
    discovery_url = "https://computerlove.eu.auth0.com/.well-known/openid-configuration"
    settings = MCPAppSettings(
        endpoints=PublicEndpointSettings(mcp_base_url=public_origin),
        mcp=MCPSettings(auth_mode="oidc"),
        oidc=OIDCSettings(
            provider=provider,
            issuer_url=upstream_issuer,
            config_url=discovery_url,
            client_id="test-client-id",
            client_secret="test-client-secret",
            audience=f"{public_origin}/mcp",
            tenant_id="test-tenant",
            required_scopes=["read"],
        ),
        oauth_storage=OIDCOAuthStorageSettings(
            directory=str(tmp_path / "fastmcp-oauth"),
            encryption_key=_TEST_OAUTH_STORAGE_ENCRYPTION_KEY,
        ),
    )
    discovery_response = httpx2.Response(
        200,
        request=httpx2.Request("GET", discovery_url),
        json={
            "issuer": "https://computerlove.eu.auth0.com/",
            "authorization_endpoint": "https://computerlove.eu.auth0.com/authorize",
            "token_endpoint": "https://computerlove.eu.auth0.com/oauth/token",
            "jwks_uri": "https://computerlove.eu.auth0.com/.well-known/jwks.json",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
        },
    )

    with patch("fastmcp.server.auth.oidc_proxy.httpx2.get", return_value=discovery_response):
        auth_provider = MCPAuthProviderFactory().create(settings)
        with TestClient(create_test_mcp_http_app(settings, auth_provider=auth_provider)) as client:
            resource_response = client.get("/.well-known/oauth-protected-resource/mcp")
            authorization_response = client.get("/.well-known/oauth-authorization-server")

    assert resource_response.status_code == 200
    resource_metadata = resource_response.json()
    assert resource_metadata["resource"] == f"{public_origin}/mcp"
    assert resource_metadata["authorization_servers"] == [f"{public_origin}/"]
    assert authorization_response.status_code == 200
    authorization_metadata = authorization_response.json()
    assert authorization_metadata["issuer"] == f"{public_origin}/"
    assert authorization_metadata["authorization_endpoint"] == f"{public_origin}/authorize"
    assert authorization_metadata["token_endpoint"] == f"{public_origin}/token"
    assert authorization_metadata["registration_endpoint"] == f"{public_origin}/register"
    assert settings.oidc.issuer_url == upstream_issuer
    if provider == "auth0":
        assert str(auth_provider.oidc_config.issuer) == upstream_issuer
        upstream_verifier = auth_provider.get_token_verifier(audience=settings.oidc.audience)
        assert upstream_verifier.issuer == upstream_issuer
        assert upstream_verifier.audience == settings.oidc.audience


def test_single_test_user_oauth_endpoints_are_available_for_local_mcp_clients() -> None:
    settings = MCPAppSettings(
        mcp=MCPSettings(auth_mode="single_test_user", _env_file=None),
        _env_file=None,
    )

    with TestClient(create_test_mcp_http_app(settings)) as client:
        registration_response = client.post("/register", json={})
        authorization_metadata_response = client.get("/.well-known/oauth-authorization-server")

    assert registration_response.status_code != 404
    assert authorization_metadata_response.status_code == 200


def test_mcp_tool_request_without_bearer_token_is_rejected_before_tool_execution() -> None:
    settings = MCPAppSettings(_env_file=None)

    with TestClient(create_test_mcp_http_app(settings)) as client:
        response = _request_mcp_tool_list_without_token(client)

    assert response.status_code == 401


def test_none_auth_mode_accepts_mcp_client_without_bearer_token() -> None:
    settings = MCPAppSettings(
        mcp=MCPSettings(auth_mode="none", _env_file=None),
        _env_file=None,
    )

    with TestClient(create_test_mcp_http_app(settings)) as client:
        response = _request_mcp_tool_list_without_token(client)

    assert response.status_code not in (401, 403)


def test_mcp_resource_request_without_bearer_token_is_rejected() -> None:
    settings = MCPAppSettings(_env_file=None)

    with TestClient(create_test_mcp_http_app(settings)) as client:
        response = client.get(
            "/mcp",
            headers={"accept": "application/json, text/event-stream"},
        )

    assert response.status_code == 401


def test_mcp_tool_request_with_invalid_bearer_token_is_rejected_before_tool_execution() -> None:
    settings = MCPAppSettings(oidc=OIDCSettings(provider="google", _env_file=None), _env_file=None)
    auth_provider = _auth_provider_for_tokens(settings, {})

    with TestClient(create_test_mcp_http_app(settings, auth_provider=auth_provider)) as client:
        response = _request_mcp_tool_list(client, "invalid-token")

    assert response.status_code == 401


def test_single_test_user_mode_accepts_configured_bearer_token_for_mcp_tools() -> None:
    settings = MCPAppSettings(
        mcp=MCPSettings(
            auth_mode="single_test_user",
            test_bearer_token=_test_jwt({"email": "alex@example.com", "groups": ["test"]}),
            _env_file=None,
        ),
        _env_file=None,
    )

    with TestClient(create_test_mcp_http_app(settings)) as client:
        response = _request_mcp_tool_list(client, settings.mcp.test_bearer_token)

    assert response.status_code != 401
    assert response.status_code != 403


def test_single_test_user_mode_rejects_incorrect_bearer_token() -> None:
    settings = MCPAppSettings(
        mcp=MCPSettings(
            auth_mode="single_test_user",
            test_bearer_token=_test_jwt({"email": "alex@example.com", "groups": ["test"]}),
            _env_file=None,
        ),
        _env_file=None,
    )

    with TestClient(create_test_mcp_http_app(settings)) as client:
        response = _request_mcp_tool_list(client, "incorrect-test-token")

    assert response.status_code == 401


def test_injected_auth_provider_takes_precedence_over_single_test_user_settings() -> None:
    settings = MCPAppSettings(
        mcp=MCPSettings(
            auth_mode="single_test_user",
            test_bearer_token=_test_jwt({"email": "alex@example.com", "groups": ["test"]}),
            _env_file=None,
        ),
        _env_file=None,
    )
    auth_provider = _auth_provider_for_tokens(settings, {"injected-token": "casey@example.com"})

    with TestClient(create_test_mcp_http_app(settings, auth_provider=auth_provider)) as client:
        rejected_response = _request_mcp_tool_list(client, settings.mcp.test_bearer_token)
        accepted_response = _request_mcp_tool_list(client, "injected-token")

    assert rejected_response.status_code == 401
    assert accepted_response.status_code != 401
    assert accepted_response.status_code != 403


def test_valid_user_token_is_sufficient_without_acl_or_role_claims() -> None:
    settings = MCPAppSettings(oidc=OIDCSettings(provider="google", _env_file=None), _env_file=None)
    auth_provider = _auth_provider_for_tokens(
        settings,
        {"google-valid-token-without-role": "alex@example.com"},
    )

    with TestClient(create_test_mcp_http_app(settings, auth_provider=auth_provider)) as client:
        response = _request_mcp_tool_list(client, "google-valid-token-without-role")

    assert response.status_code != 401
    assert response.status_code != 403


def _auth_provider_for_tokens(
    settings: MCPAppSettings,
    valid_tokens: dict[str, str],
) -> TokenValidatorAuthProvider:
    return TokenValidatorAuthProvider(
        FakeTokenValidator(valid_tokens),
        settings.endpoints.mcp_base_url,
    )


def _request_mcp_tool_list(client: TestClient, token: str) -> Response:
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={
            "accept": "application/json, text/event-stream",
            "authorization": f"Bearer {token}",
        },
    )


def _request_mcp_tool_list_without_token(client: TestClient) -> Response:
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"accept": "application/json, text/event-stream"},
    )


def _test_jwt(claims: dict[str, object]) -> str:
    return jwt.encode(claims, key="", algorithm="none")
