from pytest import MonkeyPatch

from umbod.config import OperatorSettings, load_app_config_without_env_file


def _operator(monkeypatch: MonkeyPatch, **env: str) -> OperatorSettings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return OperatorSettings(_env_file=None)


def test_defaults_are_local_dev_profile() -> None:
    operator = OperatorSettings(_env_file=None)

    assert operator.profile == "local"
    assert operator.auth is None
    assert operator.public_site_origin == "http://localhost:3010"
    assert operator.public_api_origin == "http://localhost:18010"
    assert operator.public_mcp_origin == "http://localhost:8011"
    assert operator.rest_port == 8000
    assert operator.rest_metrics_port == 8001
    assert operator.mcp_metrics_port == 8012


def test_rest_ports_read_canonical_names(monkeypatch: MonkeyPatch) -> None:
    operator = _operator(
        monkeypatch,
        UMBOD_REST_PORT="9000",
        UMBOD_REST_METRICS_PORT="9001",
    )

    assert operator.rest_port == 9000
    assert operator.rest_metrics_port == 9001


def test_mcp_metrics_port_reads_canonical_name(monkeypatch: MonkeyPatch) -> None:
    operator = _operator(monkeypatch, UMBOD_MCP_METRICS_PORT="9012")

    assert operator.mcp_metrics_port == 9012


def test_mcp_administrator_feature_defaults_to_enabled() -> None:
    operator = OperatorSettings(_env_file=None)

    assert operator.feature_mcp_administrator_enabled is True


def test_mcp_administrator_feature_reads_canonical_name(
    monkeypatch: MonkeyPatch,
) -> None:
    operator = _operator(
        monkeypatch,
        UMBOD_FEATURE_MCP_ADMINISTRATOR_ENABLED="false",
    )

    assert operator.feature_mcp_administrator_enabled is False
    assert load_app_config_without_env_file().feature_toggles.mcp_administrator_enabled is False


def test_topology_reads_canonical_names(monkeypatch: MonkeyPatch) -> None:
    operator = _operator(
        monkeypatch,
        UMBOD_PUBLIC_SITE_ORIGIN="https://admin.example.com",
        UMBOD_PUBLIC_API_ORIGIN="https://api.example.com",
        UMBOD_PUBLIC_MCP_ORIGIN="https://mcp.example.com",
        UMBOD_INTERNAL_API_ORIGIN="http://api:8000",
    )

    assert operator.public_site_origin == "https://admin.example.com"
    assert operator.public_api_origin == "https://api.example.com"
    assert operator.public_mcp_origin == "https://mcp.example.com"
    assert operator.internal_api_origin == "http://api:8000"


def test_legacy_topology_names_have_no_effect(monkeypatch: MonkeyPatch) -> None:
    operator = _operator(
        monkeypatch,
        PUBLIC_SITE_BASE_URL="https://legacy-site.example.com",
        PUBLIC_API_BASE_URL="https://legacy-api.example.com",
        PUBLIC_MCP_BASE_URL="https://legacy-mcp.example.com",
        PRIVATE_API_BASE_URL="http://legacy-api:8000",
    )

    assert operator.public_site_origin == "http://localhost:3010"
    assert operator.public_api_origin == "http://localhost:18010"
    assert operator.public_mcp_origin == "http://localhost:8011"
    assert operator.internal_api_origin == ""


def test_required_scopes_parses_comma_separated_value(monkeypatch: MonkeyPatch) -> None:
    operator = _operator(monkeypatch, UMBOD_OIDC_REQUIRED_SCOPES="openid,email, profile")

    assert operator.oidc_required_scopes == ["openid", "email", "profile"]


def test_legacy_backend_aliases_have_no_effect(monkeypatch: MonkeyPatch) -> None:
    operator = _operator(
        monkeypatch,
        UMBOD_OAUTH_STORAGE_ENCRYPTION_KEY="legacy-key",
        UMBOD_MCP_PERMISSION_GROUP_CLAIM="roles",
    )

    assert "token_encryption_key" not in operator.model_dump()
    assert operator.mcp_permission_claim is None


def test_admin_and_mcp_claims_are_independent(monkeypatch: MonkeyPatch) -> None:
    operator = _operator(
        monkeypatch,
        UMBOD_ADMIN_MEMBERSHIP_CLAIM="https://example.com/claims/groups",
        UMBOD_MCP_PERMISSION_CLAIM="groups",
    )

    assert operator.admin_membership_claim == "https://example.com/claims/groups"
    assert operator.mcp_permission_claim == "groups"


def test_default_load_is_zero_config_local() -> None:
    config = load_app_config_without_env_file()

    assert config.admin_authentication.mode == "simulation"
    assert config.mcp.auth_mode == "single_test_user"
    assert config.connector_store.type == "inmemory"
    assert config.cors.origins == ["http://localhost:3010"]
