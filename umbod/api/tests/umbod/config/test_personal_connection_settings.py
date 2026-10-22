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
from umbod.config.derive import build_app_config, load_app_config_without_env_file
from umbod.config.inspection import inspect_app_config
from umbod.config.operator import OperatorSettings, PersonalConnectionsMode


def test_unconfigured_local_development_enables_personal_connections() -> None:
    settings = build_app_config(OperatorSettings(_env_file=None))
    assert settings.personal_connections.enabled
    assert settings.personal_connections.identity_namespace == "test:umbod-local"
    assert not settings.personal_connections.oauth_enabled
    assert settings.connector_security.configuration_secret == ""
    assert not AppConfig().personal_connections.enabled
    assert AppConfig().personal_connections.identity_namespace == ""


@pytest.mark.parametrize(
    "mode,namespace,enabled",
    [
        ("auto", "", True),
        ("auto", "test:explicit", True),
        (True, "test:explicit", True),
        (False, "", False),
        (False, "test:explicit", False),
        (False, " ", False),
    ],
)
def test_local_personal_connections_preserve_explicit_settings(
    mode: PersonalConnectionsMode, namespace: str, enabled: bool
) -> None:
    settings = build_app_config(
        OperatorSettings(
            _env_file=None,
            personal_connections_enabled=mode,
            personal_connections_identity_namespace=namespace,
        )
    )
    assert settings.personal_connections.enabled is enabled
    assert settings.personal_connections.identity_namespace == (
        "test:umbod-local" if mode == "auto" and namespace == "" else namespace
    )


@pytest.mark.parametrize("auth", [None, "dev"])
def test_local_namespace_resolution_is_repeatable_without_mutating_operator(
    auth: str | None,
) -> None:
    operator = OperatorSettings(_env_file=None, auth=auth)
    original = operator.model_dump()
    first = build_app_config(operator)
    second = build_app_config(operator)
    assert first.personal_connections == second.personal_connections
    assert first.personal_connections.identity_namespace == "test:umbod-local"
    assert operator.model_dump() == original


def test_empty_compose_environment_resolves_shared_api_and_mcp_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UMBOD_PROFILE", "local")
    monkeypatch.setenv("UMBOD_AUTH", "dev")
    monkeypatch.setenv("UMBOD_PERSONAL_CONNECTIONS_ENABLED", "auto")
    monkeypatch.setenv("UMBOD_PERSONAL_CONNECTIONS_IDENTITY_NAMESPACE", "")
    monkeypatch.setenv("UMBOD_CONNECTOR_STORE", "sqlite")
    monkeypatch.setenv("UMBOD_ROOT_SECRET", "")
    api_config = load_app_config_without_env_file()
    mcp_config = load_app_config_without_env_file()
    assert api_config.personal_connections == mcp_config.personal_connections
    assert api_config.personal_connections.enabled
    assert api_config.personal_connections.identity_namespace == "test:umbod-local"
    assert not api_config.personal_connections.oauth_enabled
    assert api_config.connector_security.configuration_secret == ""


@pytest.mark.parametrize("auth", ["none", "auth0", "entra", "google"])
def test_local_non_development_auth_has_no_personal_namespace_fallback(
    auth: str,
) -> None:
    config = build_app_config(_identity_operator("local", auth))
    assert not config.personal_connections.enabled
    assert config.personal_connections.identity_namespace == ""


@pytest.mark.parametrize("auth", ["auth0", "entra", "google"])
def test_production_has_no_personal_namespace_fallback(auth: str) -> None:
    config = build_app_config(_identity_operator("production", auth))
    assert not config.personal_connections.enabled
    assert config.personal_connections.identity_namespace == ""


@pytest.mark.parametrize("auth", ["auth0", "entra", "google"])
def test_production_preserves_explicit_personal_identity_authority(auth: str) -> None:
    operator = _identity_operator("production", auth).model_copy(
        update={"personal_connections_identity_namespace": "production-authority"}
    )
    config = build_app_config(operator)
    assert config.personal_connections.enabled
    assert config.personal_connections.identity_namespace == "production-authority"


def _identity_operator(profile: str, auth: str) -> OperatorSettings:
    return OperatorSettings(
        _env_file=None,
        profile=profile,
        auth=auth,
        root_secret="identity-policy-test-secret",
        oidc_domain="identity.example.com",
        oidc_tenant_id="tenant",
        oidc_client_id="client",
        oidc_client_secret="client-secret",
        oidc_audience="api",
        oidc_issuer_url="https://identity.example.com/",
        oidc_required_scopes=["api.read"],
    )


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
