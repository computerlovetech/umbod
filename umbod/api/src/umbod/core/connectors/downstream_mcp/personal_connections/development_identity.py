from collections.abc import Mapping

from umbod.config.app import AppConfig

from .development_identity_models import SimulatedUserIdentity


def local_personal_identity_enabled(settings: AppConfig) -> bool:
    namespace = settings.personal_connections.identity_namespace
    return (
        settings.runtime.profile == "local"
        and settings.runtime.auth == "dev"
        and settings.admin_authentication.mode == "simulation"
        and settings.admin_authentication.environment == "development"
        and settings.personal_connections.enabled
        and namespace == namespace.strip()
        and namespace.startswith("test:")
        and bool(namespace.removeprefix("test:").strip())
        and bool(settings.admin_authentication.simulated_user_id.strip())
    )


def simulated_user_claims(identity: SimulatedUserIdentity) -> dict[str, object]:
    claims: dict[str, object] = {
        "sub": identity.user_id, "email": identity.email, "name": identity.name,
    }
    if identity.simulated_admin:
        claims[identity.membership_claim] = [identity.required_membership]
    return claims


def machine_identity(claims: Mapping[str, object]) -> bool:
    subject = claims.get("sub")
    email = claims.get("email")
    return (
        claims.get("idtyp") == "app"
        or claims.get("gty") in ("client-credentials", "client_credentials")
        or claims.get("grant_type") == "client_credentials"
        or isinstance(subject, str) and subject.endswith("@clients")
        or isinstance(email, str) and email.endswith(".gserviceaccount.com")
    )


def authenticated_personal_mcp_claims(
    settings: AppConfig, claims: Mapping[str, object]
) -> Mapping[str, object]:
    if machine_identity(claims):
        return {}
    if not (local_personal_identity_enabled(settings) and settings.mcp.auth_mode == "single_test_user"):
        return claims
    authentication = settings.admin_authentication
    return simulated_user_claims(SimulatedUserIdentity(
        user_id=authentication.simulated_user_id,
        email=authentication.simulated_user_email,
        name=authentication.simulated_user_name,
        membership_claim=authentication.membership_claim,
        required_membership=authentication.required_membership,
        simulated_admin=authentication.simulated_admin,
    ))
