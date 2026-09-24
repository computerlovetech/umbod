from pytest import MonkeyPatch

from umbod.config import OperatorSettings, build_app_config

_ROOT_SECRET = "production-root-secret-with-sufficient-entropy"


def _config(monkeypatch: MonkeyPatch, **env: str):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return build_app_config(OperatorSettings(_env_file=None))


def test_local_dev_recipe_uses_simulation_and_single_test_user(monkeypatch: MonkeyPatch) -> None:
    config = _config(monkeypatch)

    assert config.admin_authentication.environment == "development"
    assert config.admin_authentication.mode == "simulation"
    assert config.mcp.auth_mode == "single_test_user"
    assert config.rest.port == 8000
    assert config.rest.metrics_port == 8001
    assert config.mcp.metrics_port == 8012


def test_local_none_recipe_disables_admin_and_mcp_auth(monkeypatch: MonkeyPatch) -> None:
    config = _config(monkeypatch, UMBOD_AUTH="none")

    assert config.admin_authentication.mode == "disabled"
    assert config.mcp.auth_mode == "none"


def test_rest_ports_are_built_from_operator_settings(monkeypatch: MonkeyPatch) -> None:
    config = _config(
        monkeypatch,
        UMBOD_REST_PORT="9000",
        UMBOD_REST_METRICS_PORT="9001",
    )

    assert config.rest.port == 9000
    assert config.rest.metrics_port == 9001


def test_mcp_metrics_port_is_built_from_operator_setting(monkeypatch: MonkeyPatch) -> None:
    config = _config(monkeypatch, UMBOD_MCP_METRICS_PORT="9012")

    assert config.mcp.metrics_port == 9012


def test_cors_origins_default_to_site_origin(monkeypatch: MonkeyPatch) -> None:
    config = _config(monkeypatch, UMBOD_PUBLIC_SITE_ORIGIN="https://admin.example.com")

    assert config.cors.origins == ["https://admin.example.com"]


def test_sqlite_path_derived_from_data_dir(monkeypatch: MonkeyPatch) -> None:
    config = _config(monkeypatch, UMBOD_DATA_DIR="/app/data")

    assert config.connector_store.sqlite_path == "/app/data/umbod.sqlite3"
    assert config.oauth_storage.directory == "/app/data/fastmcp-oauth"


def test_auth0_recipe_derives_discovery_and_jwks(monkeypatch: MonkeyPatch) -> None:
    config = _config(
        monkeypatch,
        UMBOD_PROFILE="production",
        UMBOD_AUTH="auth0",
        UMBOD_OIDC_DOMAIN="example.eu.auth0.com",
        UMBOD_OIDC_CLIENT_ID="client-id",
        UMBOD_OIDC_CLIENT_SECRET="client-secret",
        UMBOD_OIDC_AUDIENCE="https://api.example.com",
        UMBOD_ROOT_SECRET=_ROOT_SECRET,
    )

    assert config.mcp.auth_mode == "oidc"
    assert config.oidc.provider == "auth0"
    assert config.oidc.config_url == "https://example.eu.auth0.com/.well-known/openid-configuration"
    assert config.oidc.issuer_url == ""
    assert config.admin_authentication.mode == "jwt"
    assert config.admin_authentication.environment == "production"
    assert (
        config.admin_authentication.jwks_url == "https://example.eu.auth0.com/.well-known/jwks.json"
    )
    assert config.admin_authentication.membership_claim == "permissions"


def test_root_secret_derives_independent_backend_security_keys(
    monkeypatch: MonkeyPatch,
) -> None:
    config = _config(
        monkeypatch,
        UMBOD_PROFILE="production",
        UMBOD_AUTH="auth0",
        UMBOD_OIDC_DOMAIN="example.eu.auth0.com",
        UMBOD_OIDC_CLIENT_ID="client-id",
        UMBOD_OIDC_CLIENT_SECRET="client-secret",
        UMBOD_OIDC_AUDIENCE="https://api.example.com",
        UMBOD_ROOT_SECRET=_ROOT_SECRET,
    )

    repeated = _config(monkeypatch, UMBOD_ROOT_SECRET=_ROOT_SECRET)
    secrets = (
        config.oidc.jwt_signing_key,
        config.oauth_storage.encryption_key,
        config.connector_security.configuration_secret,
        config.connector_security.approval_state_key,
    )
    repeated_secrets = (
        repeated.oidc.jwt_signing_key,
        repeated.oauth_storage.encryption_key,
        repeated.connector_security.configuration_secret,
        repeated.connector_security.approval_state_key,
    )
    assert len(set(secrets)) == 4
    assert all(secrets)
    assert secrets == repeated_secrets


def test_removed_purpose_secret_environment_variables_have_no_effect(
    monkeypatch: MonkeyPatch,
) -> None:
    config = _config(
        monkeypatch,
        UMBOD_ROOT_SECRET=_ROOT_SECRET,
        UMBOD_JWT_SIGNING_KEY="ignored-jwt-key",
        UMBOD_TOKEN_ENCRYPTION_KEY="ignored-token-key",
        UMBOD_CONNECTOR_CONFIGURATION_SECRET="ignored-configuration-key",
        UMBOD_CONNECTOR_APPROVAL_STATE_KEY="ignored-approval-key",
    )

    assert config.oidc.jwt_signing_key != "ignored-jwt-key"
    assert config.oauth_storage.encryption_key != "ignored-token-key"
    assert config.connector_security.configuration_secret != "ignored-configuration-key"
    assert config.connector_security.approval_state_key != "ignored-approval-key"


def test_local_empty_root_preserves_empty_internal_security_keys(
    monkeypatch: MonkeyPatch,
) -> None:
    config = _config(monkeypatch, UMBOD_ROOT_SECRET="")

    assert config.oidc.jwt_signing_key == ""
    assert config.oauth_storage.encryption_key == ""
    assert config.connector_security.configuration_secret == ""
    assert config.connector_security.approval_state_key == ""


def test_admin_and_mcp_permission_claims_can_differ(monkeypatch: MonkeyPatch) -> None:
    config = _config(
        monkeypatch,
        UMBOD_PROFILE="production",
        UMBOD_AUTH="auth0",
        UMBOD_OIDC_DOMAIN="example.eu.auth0.com",
        UMBOD_OIDC_CLIENT_ID="client-id",
        UMBOD_OIDC_CLIENT_SECRET="client-secret",
        UMBOD_OIDC_AUDIENCE="https://api.example.com",
        UMBOD_ROOT_SECRET=_ROOT_SECRET,
        UMBOD_ADMIN_MEMBERSHIP_CLAIM="https://api.example.com/claims/groups",
        UMBOD_MCP_PERMISSION_CLAIM="groups",
    )

    assert config.admin_authentication.membership_claim == "https://api.example.com/claims/groups"
    assert config.mcp.permission_group_claim == "groups"
