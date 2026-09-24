from pytest import MonkeyPatch, raises

from umbod.config import (
    OperatorSettings,
    build_app_config,
    load_app_config_without_env_file,
)



def _config(monkeypatch: MonkeyPatch, **env: str):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return build_app_config(OperatorSettings(_env_file=None))


def test_cors_origins_accepts_comma_separated_env_value(monkeypatch: MonkeyPatch) -> None:
    raw_origins = "http://localhost:3010, http://localhost:5173,,https://example.com"
    expected_origins = [
        "http://localhost:3010",
        "http://localhost:5173",
        "https://example.com",
    ]

    settings = _config(monkeypatch, UMBOD_CORS_ORIGINS=raw_origins)

    assert settings.cors.origins == expected_origins


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


def test_admin_authentication_defaults_to_development_simulation() -> None:
    settings = load_app_config_without_env_file()

    assert settings.admin_authentication.environment == "development"
    assert settings.admin_authentication.mode == "simulation"
    assert settings.admin_authentication.simulated_admin is True


def test_admin_authentication_production_rejects_dev_auth(monkeypatch: MonkeyPatch) -> None:
    with raises(ValueError):
        _config(monkeypatch, UMBOD_PROFILE="production", UMBOD_AUTH="dev")


def test_admin_authentication_production_jwt_derives_jwks_url(monkeypatch: MonkeyPatch) -> None:
    settings = _config(
        monkeypatch,
        UMBOD_PROFILE="production",
        UMBOD_AUTH="auth0",
        UMBOD_OIDC_DOMAIN="identity.example.com",
        UMBOD_OIDC_CLIENT_ID="client-id",
        UMBOD_OIDC_CLIENT_SECRET="client-secret",
        UMBOD_OIDC_AUDIENCE="https://api.example.com",
        UMBOD_ROOT_SECRET="production-root-secret-with-sufficient-entropy",
        UMBOD_ADMIN_GROUP="admin",
    )

    assert settings.admin_authentication.environment == "production"
    assert settings.admin_authentication.mode == "jwt"
    assert (
        settings.admin_authentication.jwks_url
        == "https://identity.example.com/.well-known/jwks.json"
    )
    assert settings.admin_authentication.required_membership == "admin"
