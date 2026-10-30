from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER

from .app import AppConfig


def local_development_identity_enabled(settings: AppConfig) -> bool:
    return (
        settings.runtime.profile == "local"
        and settings.runtime.auth == "dev"
        and settings.admin_authentication.mode == "simulation"
        and settings.admin_authentication.environment == "development"
        and bool(settings.admin_authentication.simulated_user_id.strip())
    )


def filesystem_managed_issuer(settings: AppConfig) -> str:
    if local_development_identity_enabled(settings):
        return LOCAL_DEVELOPMENT_ISSUER
    return settings.oidc.issuer_url
