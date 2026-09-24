import jwt
from pytest import MonkeyPatch, raises

from umbod.config import (
    OperatorSettings,
    build_app_config,
    load_app_config_without_env_file,
)
from umbod.mcp.public_app import api_base_url_from_settings
from umbod.mcp.settings import MCPSettings



def _config(monkeypatch: MonkeyPatch, **env: str):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return build_app_config(OperatorSettings(_env_file=None))


def test_mcp_settings_default_to_single_test_user() -> None:
    settings = load_app_config_without_env_file()

    assert settings.mcp.auth_mode == "single_test_user"
    assert settings.mcp.test_user_email == "test-user@example.com"
    assert jwt.decode(settings.mcp.test_bearer_token, options={"verify_signature": False})[
        "groups"
    ] == ["test"]
    assert settings.mcp.test_user_group == "test-group"
    assert settings.mcp.permission_group_claim == "groups"
    assert settings.mcp.auth_debug_enabled is False


def test_mcp_settings_admit_codemode_with_default_execution_timeout() -> None:
    settings = MCPSettings(connector_tool_exposure_mode="codemode")

    assert settings.connector_tool_exposure_mode == "codemode"
    assert settings.connector_code_execution_timeout_seconds == 30.0


def test_mcp_settings_accept_positive_code_execution_timeout() -> None:
    settings = MCPSettings(connector_code_execution_timeout_seconds=4.5)

    assert settings.connector_code_execution_timeout_seconds == 4.5


def test_mcp_settings_reject_non_positive_code_execution_timeout() -> None:
    with raises(ValueError):
        MCPSettings(connector_code_execution_timeout_seconds=0)


def test_mcp_settings_use_existing_environment_variable_names(monkeypatch: MonkeyPatch) -> None:
    settings = _config(
        monkeypatch,
        UMBOD_MCP_PORT="9999",
        UMBOD_MCP_TEST_USER_EMAIL="alex@example.com",
        UMBOD_MCP_TEST_BEARER_TOKEN="test-token",
        UMBOD_MCP_TEST_USER_GROUP="test-users",
        UMBOD_MCP_PERMISSION_CLAIM="roles",
        UMBOD_MCP_AUTH_DEBUG_ENABLED="true",
    )

    assert settings.mcp.port == 9999
    assert settings.mcp.auth_mode == "single_test_user"
    assert settings.mcp.test_user_email == "alex@example.com"
    assert settings.mcp.test_bearer_token == "test-token"
    assert settings.mcp.test_user_group == "test-users"
    assert settings.mcp.permission_group_claim == "roles"
    assert settings.mcp.auth_debug_enabled is True


def test_public_mcp_origin_uses_canonical_name(monkeypatch: MonkeyPatch) -> None:
    settings = _config(monkeypatch, UMBOD_PUBLIC_MCP_ORIGIN="https://umbod.computerlove.tech")

    assert settings.endpoints.mcp_base_url == "https://umbod.computerlove.tech"


def test_connector_store_defaults_to_inmemory() -> None:
    settings = load_app_config_without_env_file()

    assert settings.connector_store.type == "inmemory"
    assert settings.connector_store.sqlite_path == ".data/umbod.sqlite3"


def test_connector_store_settings_use_environment_variable_names(monkeypatch: MonkeyPatch) -> None:
    settings = _config(
        monkeypatch,
        UMBOD_CONNECTOR_STORE="sqlite",
        UMBOD_CONNECTOR_STORE_SQLITE_PATH="/tmp/umbod.sqlite3",
    )

    assert settings.connector_store.type == "sqlite"
    assert settings.connector_store.sqlite_path == "/tmp/umbod.sqlite3"


def test_private_api_base_url_is_preferred_for_runtime_sync(monkeypatch: MonkeyPatch) -> None:
    settings = _config(
        monkeypatch,
        UMBOD_PUBLIC_API_ORIGIN="http://localhost:18010",
        UMBOD_INTERNAL_API_ORIGIN="http://api:8000",
    )

    assert api_base_url_from_settings(settings) == "http://api:8000"


def test_oauth_storage_settings_default_and_environment_values(monkeypatch: MonkeyPatch) -> None:
    settings = load_app_config_without_env_file()

    assert settings.oauth_storage.directory == ".data/fastmcp-oauth"
    assert settings.oauth_storage.encryption_key == ""

    configured = _config(
        monkeypatch,
        UMBOD_OAUTH_STORAGE_DIRECTORY="/app/data/fastmcp-oauth",
        UMBOD_ROOT_SECRET="local-root-secret",
    )

    assert configured.oauth_storage.directory == "/app/data/fastmcp-oauth"
    assert configured.oauth_storage.encryption_key


def test_single_test_user_auth_mode_requires_test_bearer_token(monkeypatch: MonkeyPatch) -> None:
    with raises(ValueError, match="UMBOD_MCP_TEST_BEARER_TOKEN"):
        _config(monkeypatch, UMBOD_MCP_TEST_BEARER_TOKEN="   ")
