from pytest import MonkeyPatch

from umbod.config import OperatorSettings, build_app_config, redact_app_config

def _config(monkeypatch: MonkeyPatch, **env: str):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return build_app_config(OperatorSettings(_env_file=None))


def test_build_app_config_returns_config_for_local_defaults(monkeypatch: MonkeyPatch) -> None:
    config = _config(monkeypatch)

    assert config.mcp.auth_mode == "single_test_user"
    assert config.admin_authentication.mode == "simulation"


def test_redaction_masks_secrets(monkeypatch: MonkeyPatch) -> None:
    config = _config(
        monkeypatch,
        UMBOD_PROFILE="production",
        UMBOD_AUTH="auth0",
        UMBOD_OIDC_DOMAIN="example.eu.auth0.com",
        UMBOD_OIDC_CLIENT_ID="client-id",
        UMBOD_OIDC_CLIENT_SECRET="super-secret",
        UMBOD_OIDC_AUDIENCE="https://api.example.com",
        UMBOD_ROOT_SECRET="production-root-secret-with-sufficient-entropy",
    )

    redacted = redact_app_config(config)

    assert redacted["oidc"]["client_secret"] == "***"
    assert redacted["oauth_storage"]["encryption_key"] == "***"
    assert redacted["oidc"]["client_id"] == "client-id"
