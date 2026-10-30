import pytest

from umbod.config import AppConfig, OidcConfig
from umbod.config.identity_policy import (
    filesystem_managed_issuer,
    local_development_identity_enabled,
)
from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER
from umbod.rest.authentication.local import local_rest_identity_enabled


@pytest.mark.parametrize("issuer", ["", "https://configured.example/exact/"])
def test_explicit_local_identity_selects_local_filesystem_issuer(issuer: str) -> None:
    config = AppConfig(oidc=OidcConfig(issuer_url=issuer))

    assert local_development_identity_enabled(config)
    assert local_rest_identity_enabled(config)
    assert filesystem_managed_issuer(config) == LOCAL_DEVELOPMENT_ISSUER


@pytest.mark.parametrize("section,updates", [
    ("runtime", {"profile": "production"}),
    ("runtime", {"auth": "auth0"}),
    ("admin_authentication", {"mode": "jwt"}),
    ("admin_authentication", {"environment": "production"}),
    ("admin_authentication", {"simulated_user_id": " \t"}),
])
def test_nonlocal_identity_preserves_exact_configured_filesystem_issuer(
    section: str, updates: dict[str, str],
) -> None:
    config = AppConfig(oidc=OidcConfig(issuer_url="https://configured.example/exact/"))
    selected = getattr(config, section).model_copy(update=updates)
    config = config.model_copy(update={section: selected})

    assert not local_development_identity_enabled(config)
    assert not local_rest_identity_enabled(config)
    assert filesystem_managed_issuer(config) == "https://configured.example/exact/"
