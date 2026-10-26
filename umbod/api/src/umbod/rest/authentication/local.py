from umbod.config import AppConfig
from umbod.core.callers import LOCAL_DEVELOPMENT_ISSUER as LOCAL_DEVELOPMENT_ISSUER


def local_rest_identity_enabled(settings: AppConfig) -> bool:
    return (
        settings.runtime.profile == "local"
        and settings.runtime.auth == "dev"
        and settings.admin_authentication.mode == "simulation"
        and settings.admin_authentication.environment == "development"
        and bool(settings.admin_authentication.simulated_user_id.strip())
    )
