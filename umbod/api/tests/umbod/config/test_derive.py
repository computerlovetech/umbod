import jwt
from pytest import MonkeyPatch, mark, raises

from umbod.config import AppConfig, OperatorSettings, build_app_config, redact_app_config
from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER

def _config(monkeypatch: MonkeyPatch, **env: str) -> AppConfig:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return build_app_config(OperatorSettings(_env_file=None))


def test_build_app_config_returns_config_for_local_defaults(monkeypatch: MonkeyPatch) -> None:
    config = _config(monkeypatch)

    assert config.mcp.auth_mode == "single_test_user"
    assert config.admin_authentication.mode == "simulation"


@mark.parametrize("issuer_claims", [{}, {"iss": LOCAL_DEVELOPMENT_ISSUER}])
def test_dev_rest_uses_the_subject_from_the_mcp_test_token(
    monkeypatch: MonkeyPatch, issuer_claims: dict[str, str],
) -> None:
    token = jwt.encode({"sub": "custom-local-user", "email": "dev@example.test", **issuer_claims}, key="", algorithm="none")
    config = _config(monkeypatch, UMBOD_MCP_TEST_BEARER_TOKEN=token)

    assert config.admin_authentication.simulated_user_id == "custom-local-user"


def test_dev_ignores_the_removed_rest_subject_override(monkeypatch: MonkeyPatch) -> None:
    config = _config(monkeypatch, UMBOD_ADMIN_AUTHENTICATION_SIMULATED_USER_ID="another-local-user")

    assert config.admin_authentication.simulated_user_id == "local-test-user"


@mark.parametrize(
    ("identity_claims", "message"),
    [
        ({}, "nonblank sub"),
        ({"sub": " user "}, "nonblank sub"),
        ({"sub": "user", "email": ""}, "nonblank email"),
        ({"sub": "user", "iss": "https://issuer.example.test"}, "must omit iss"),
    ],
)
def test_dev_rejects_invalid_test_token_identity(
    monkeypatch: MonkeyPatch, identity_claims: dict[str, str], message: str,
) -> None:
    token = jwt.encode({"email": "dev@example.test", **identity_claims}, key="", algorithm="none")
    with raises(ValueError, match=message):
        _config(monkeypatch, UMBOD_MCP_TEST_BEARER_TOKEN=token)


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
