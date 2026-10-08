import pytest

from umbod.config import OperatorSettings, build_app_config


@pytest.fixture
def production_operator() -> OperatorSettings:
    return OperatorSettings(
        _env_file=None,
        profile="production",
        auth="auth0",
        root_secret="production-root-secret-with-sufficient-entropy",
        oidc_domain="example.eu.auth0.com",
        oidc_client_id="client-id",
        oidc_client_secret="client-secret",
        oidc_audience="https://api.example.com",
        oidc_tenant_id="tenant-id",
        oidc_required_scopes=["api.read"],
        oidc_issuer_url="",
    )


def test_production_auth0_derives_issuer_matching_discovery(production_operator: OperatorSettings) -> None:
    config = build_app_config(production_operator)
    assert config.oidc.issuer_url == "https://example.eu.auth0.com/"
    assert config.oidc.config_url == config.oidc.issuer_url + ".well-known/openid-configuration"


@pytest.mark.parametrize("recipe", ["auth0", "entra", "google"])
def test_explicit_production_issuer_is_preserved(
    production_operator: OperatorSettings, recipe: str
) -> None:
    production_operator.auth = recipe
    production_operator.oidc_issuer_url = "https://configured-issuer.example.com/exact/"
    config = build_app_config(production_operator)
    assert config.oidc.issuer_url == "https://configured-issuer.example.com/exact/"


@pytest.mark.parametrize("recipe", ["entra", "google"])
def test_production_provider_without_unambiguous_issuer_requires_explicit_setting(
    production_operator: OperatorSettings, recipe: str
) -> None:
    production_operator.auth = recipe
    with pytest.raises(ValueError, match="UMBOD_OIDC_ISSUER_URL"):
        build_app_config(production_operator)


@pytest.mark.parametrize("recipe", ["auth0", "entra", "google"])
def test_production_provider_requires_audience_during_configuration_validation(
    production_operator: OperatorSettings, recipe: str
) -> None:
    production_operator.auth = recipe
    production_operator.oidc_issuer_url = "https://configured-issuer.example.com/"
    production_operator.oidc_audience = ""
    with pytest.raises(ValueError, match="UMBOD_OIDC_AUDIENCE"):
        build_app_config(production_operator)


def test_production_auth0_custom_discovery_without_domain_requires_explicit_issuer(
    production_operator: OperatorSettings,
) -> None:
    production_operator.oidc_domain = ""
    production_operator.oidc_config_url = "https://custom-issuer.example.com/.well-known/openid-configuration"
    with pytest.raises(ValueError, match="UMBOD_OIDC_ISSUER_URL"):
        build_app_config(production_operator)


def test_production_auth0_custom_discovery_preserves_explicit_issuer(
    production_operator: OperatorSettings,
) -> None:
    production_operator.oidc_domain = ""
    production_operator.oidc_config_url = "https://custom-issuer.example.com/.well-known/openid-configuration"
    production_operator.oidc_issuer_url = "https://custom-issuer.example.com/"
    config = build_app_config(production_operator)
    assert config.oidc.issuer_url == "https://custom-issuer.example.com/"
