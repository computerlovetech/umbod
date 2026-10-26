import pytest
from pydantic import ValidationError

from umbod.config import AppConfig
from umbod.rest.main import create_app


@pytest.mark.parametrize("runtime,authentication", [
    ({"profile": "production", "auth": "dev"}, {"mode": "jwt", "environment": "production"}),
    ({"profile": "production", "auth": "none"}, {"mode": "disabled", "environment": "production"}),
    ({"profile": "production", "auth": "auth0"}, {"mode": "simulation", "environment": "development"}),
    ({"profile": "production", "auth": "auth0"}, {"mode": "disabled", "environment": "development"}),
    ({"profile": "production", "auth": "auth0"}, {"mode": "jwt", "environment": "development"}),
    ({"profile": "local", "auth": "dev"}, {"mode": "simulation", "environment": "production"}),
    ({"profile": "local", "auth": "none"}, {"mode": "disabled", "environment": "production"}),
])
def test_production_rejects_insecure_rest_authentication_even_without_personal_connections(
    runtime: dict[str, str], authentication: dict[str, str],
) -> None:
    with pytest.raises(ValidationError, match="Production REST requires"):
        AppConfig(runtime=runtime, admin_authentication=authentication)
    settings = AppConfig()
    overridden = settings.model_copy(update={
        "runtime": settings.runtime.model_copy(update=runtime),
        "admin_authentication": settings.admin_authentication.model_copy(update=authentication),
    })
    with pytest.raises(ValueError, match="Production REST requires"):
        create_app(overridden, [])


@pytest.mark.parametrize("mode", ["simulation", "disabled"])
def test_local_development_retains_explicit_authentication_modes(mode: str) -> None:
    settings = AppConfig(admin_authentication={"mode": mode, "environment": "development"})
    assert settings.admin_authentication.mode == mode
