import pytest
from pydantic import ValidationError

from umbod.config.app import (
    AdminAuthConfig,
    AppConfig,
    McpConfig,
    OidcConfig,
    PersonalConnectionsConfig,
    RuntimeConfig,
)
from umbod.config.derive import build_app_config
from umbod.config.inspection import inspect_app_config
from umbod.config.operator import OperatorSettings


def test_unconfigured_deployment_keeps_personal_connections_unavailable() -> None:
    settings = build_app_config(OperatorSettings(_env_file=None))
    assert not settings.personal_connections.enabled
    assert settings.personal_connections.identity_namespace == ""
    assert not AppConfig().personal_connections.enabled


def test_personal_connections_environment_and_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_PERSONAL_CONNECTIONS_ENABLED", "true")
    monkeypatch.setenv("UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE", "test:local")
    settings = build_app_config(OperatorSettings(_env_file=None))
    assert settings.personal_connections.enabled
    entries = {
        entry.variable: entry.value
        for group in inspect_app_config(settings).groups
        for entry in group.entries
    }
    assert entries["UMBOD_PERSONAL_CONNECTIONS_ENABLED"] is True
    assert entries["UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE"] == "test:local"


@pytest.mark.parametrize("namespace", ["", " ", "authority", "test:", " test:local"])
def test_development_personal_connections_require_explicit_test_namespace(
    namespace: str,
) -> None:
    with pytest.raises(ValueError):
        build_app_config(
            OperatorSettings(
                _env_file=None,
                personal_connections_enabled=True,
                personal_connections_identity_namespace=namespace,
            )
        )


def test_unauthenticated_operator_configuration_cannot_enable_personal_connections() -> (
    None
):
    with pytest.raises(ValueError, match="authenticated"):
        build_app_config(
            OperatorSettings(
                _env_file=None,
                auth="none",
                personal_connections_enabled=True,
                personal_connections_identity_namespace="test:local",
            )
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"personal_connections": {"enabled": True}},
        {"admin_authentication": {"mode": "disabled"}},
        {"mcp": {"auth_mode": "none"}},
        {"personal_connections": {"enabled": True, "identity_namespace": "authority"}},
        {"runtime": {"profile": "production"}},
        {"admin_authentication": {"environment": "production"}},
    ],
)
def test_manual_app_configuration_cannot_bypass_identity_validation(
    changes: dict[str, object],
) -> None:
    data: dict[str, object] = {
        "personal_connections": {"enabled": True, "identity_namespace": "test:local"},
    }
    data.update(changes)
    with pytest.raises(ValidationError):
        AppConfig.model_validate(data)


@pytest.mark.parametrize(
    "profile,namespace,error",
    [
        ("production", "authority", "Production personal connections"),
        ("production", "test:local", "Production personal connections"),
        ("local", "authority", "test: identity namespace"),
    ],
)
def test_manual_development_jwt_environment_cannot_bypass_identity_isolation(
    profile: str, namespace: str, error: str
) -> None:
    with pytest.raises(ValidationError, match=error):
        AppConfig(
            runtime=RuntimeConfig(profile=profile, auth="google"),
            admin_authentication=AdminAuthConfig(
                mode="jwt", environment="development", jwks_url="https://upstream/keys"
            ),
            mcp=McpConfig(auth_mode="oidc"),
            oidc=OidcConfig(
                provider="google", issuer_url="https://upstream/", audience="api"
            ),
            personal_connections=PersonalConnectionsConfig(
                enabled=True, identity_namespace=namespace
            ),
        )


def test_local_development_jwt_environment_allows_explicit_test_namespace() -> None:
    settings = AppConfig(
        runtime=RuntimeConfig(profile="local", auth="google"),
        admin_authentication=AdminAuthConfig(mode="jwt", environment="development"),
        mcp=McpConfig(auth_mode="oidc"),
        personal_connections=PersonalConnectionsConfig(
            enabled=True, identity_namespace="test:local"
        ),
    )
    assert settings.personal_connections.enabled


def _production() -> dict[str, object]:
    return {
        "runtime": {"profile": "production", "auth": "google"},
        "admin_authentication": {
            "environment": "production",
            "mode": "jwt",
            "jwks_url": "https://upstream/keys",
        },
        "mcp": {"auth_mode": "oidc"},
        "oidc": {
            "provider": "google",
            "issuer_url": "https://upstream/",
            "audience": "api",
        },
        "personal_connections": {"enabled": True, "identity_namespace": "authority"},
    }


def test_complete_production_identity_policy_is_valid() -> None:
    assert AppConfig.model_validate(_production()).personal_connections.enabled


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("oidc", "issuer_url", ""),
        ("oidc", "audience", ""),
        ("admin_authentication", "jwks_url", ""),
        ("admin_authentication", "mode", "simulation"),
        ("mcp", "auth_mode", "single_test_user"),
        ("oidc", "provider", "unsupported"),
        ("oidc", "provider", "azure_entra_id"),
    ],
)
def test_production_rejects_incomplete_identity_policy(
    section: str, field: str, value: str
) -> None:
    data = _production()
    section_data = data[section]
    assert isinstance(section_data, dict)
    section_data[field] = value
    with pytest.raises(ValidationError):
        AppConfig.model_validate(data)
