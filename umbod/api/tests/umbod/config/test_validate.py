from pydantic import ValidationError
from pytest import MonkeyPatch, raises

from umbod.config import OperatorSettings, build_app_config

_ROOT_SECRET = "production-root-secret-with-sufficient-entropy"


def _config(monkeypatch: MonkeyPatch, **env: str):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return build_app_config(OperatorSettings(_env_file=None))


def test_rest_ports_must_be_positive(monkeypatch: MonkeyPatch) -> None:
    with raises(ValidationError, match="UMBOD_REST_PORT"):
        _config(monkeypatch, UMBOD_REST_PORT="0")

    with raises(ValidationError, match="UMBOD_REST_METRICS_PORT"):
        _config(monkeypatch, UMBOD_REST_METRICS_PORT="0")


def test_rest_ports_must_be_distinct_from_all_service_ports(monkeypatch: MonkeyPatch) -> None:
    collisions = (
        ("UMBOD_REST_METRICS_PORT", "8000"),
        ("UMBOD_MCP_PORT", "8000"),
        ("UMBOD_MCP_METRICS_PORT", "8000"),
        ("UMBOD_MCP_PORT", "8001"),
        ("UMBOD_MCP_METRICS_PORT", "8001"),
    )

    for env_name, value in collisions:
        with raises(ValueError, match=env_name):
            _config(monkeypatch, **{env_name: value})
        monkeypatch.delenv(env_name)


def test_mcp_metrics_port_must_be_positive(monkeypatch: MonkeyPatch) -> None:
    with raises(ValidationError, match="UMBOD_MCP_METRICS_PORT"):
        _config(monkeypatch, UMBOD_MCP_METRICS_PORT="0")


def test_mcp_metrics_port_must_be_distinct_from_mcp_port(monkeypatch: MonkeyPatch) -> None:
    with raises(ValueError, match="UMBOD_MCP_METRICS_PORT"):
        _config(
            monkeypatch,
            UMBOD_MCP_PORT="9011",
            UMBOD_MCP_METRICS_PORT="9011",
        )


def test_production_rejects_dev_auth(monkeypatch: MonkeyPatch) -> None:
    with raises(ValueError, match="UMBOD_AUTH"):
        _config(monkeypatch, UMBOD_PROFILE="production", UMBOD_AUTH="dev")


def test_production_rejects_none_auth(monkeypatch: MonkeyPatch) -> None:
    with raises(ValueError, match="UMBOD_AUTH"):
        _config(monkeypatch, UMBOD_PROFILE="production", UMBOD_AUTH="none")


def test_production_requires_explicit_auth(monkeypatch: MonkeyPatch) -> None:
    with raises(ValueError, match="UMBOD_AUTH"):
        _config(monkeypatch, UMBOD_PROFILE="production")


def test_auth0_recipe_requires_client_id(monkeypatch: MonkeyPatch) -> None:
    with raises(ValueError, match="UMBOD_OIDC_CLIENT_ID"):
        _config(
            monkeypatch,
            UMBOD_PROFILE="production",
            UMBOD_AUTH="auth0",
            UMBOD_OIDC_DOMAIN="example.eu.auth0.com",
            UMBOD_ROOT_SECRET=_ROOT_SECRET,
        )


def test_auth0_recipe_requires_audience(monkeypatch: MonkeyPatch) -> None:
    with raises(ValueError, match="UMBOD_OIDC_AUDIENCE"):
        _config(
            monkeypatch,
            UMBOD_PROFILE="production",
            UMBOD_AUTH="auth0",
            UMBOD_OIDC_DOMAIN="example.eu.auth0.com",
            UMBOD_OIDC_CLIENT_ID="client-id",
            UMBOD_OIDC_CLIENT_SECRET="client-secret",
            UMBOD_ROOT_SECRET=_ROOT_SECRET,
        )


def test_entra_recipe_requires_tenant_and_scopes(monkeypatch: MonkeyPatch) -> None:
    with raises(ValueError, match="UMBOD_OIDC_TENANT_ID"):
        _config(
            monkeypatch,
            UMBOD_PROFILE="production",
            UMBOD_AUTH="entra",
            UMBOD_OIDC_CLIENT_ID="client-id",
            UMBOD_ROOT_SECRET=_ROOT_SECRET,
        )

    with raises(ValueError, match="UMBOD_OIDC_REQUIRED_SCOPES"):
        _config(
            monkeypatch,
            UMBOD_PROFILE="production",
            UMBOD_AUTH="entra",
            UMBOD_OIDC_CLIENT_ID="client-id",
            UMBOD_OIDC_TENANT_ID="tenant-id",
            UMBOD_ROOT_SECRET=_ROOT_SECRET,
        )


def test_production_requires_root_secret(monkeypatch: MonkeyPatch) -> None:
    with raises(ValueError, match="UMBOD_ROOT_SECRET"):
        _config(
            monkeypatch,
            UMBOD_PROFILE="production",
            UMBOD_AUTH="google",
            UMBOD_OIDC_CLIENT_ID="client-id",
        )
