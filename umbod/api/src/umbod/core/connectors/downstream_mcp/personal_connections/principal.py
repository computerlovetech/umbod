from collections.abc import Mapping
from typing import Optional

from umbod.config.app import AppConfig
from umbod.core.connectors.downstream_mcp.personal_connections.models import (
    CanonicalPrincipal,
)


def _string_claim(claims: Mapping[str, object], name: str) -> str:
    value = claims.get(name)
    return value if isinstance(value, str) and value.strip() else ""


def _machine_identity(claims: Mapping[str, object]) -> bool:
    subject = _string_claim(claims, "sub")
    email = _string_claim(claims, "email")
    return (
        claims.get("idtyp") == "app"
        or claims.get("gty") in ("client-credentials", "client_credentials")
        or claims.get("grant_type") == "client_credentials"
        or subject.endswith("@clients")
        or email.endswith(".gserviceaccount.com")
    )


def canonical_principal(
    settings: AppConfig, claims: Mapping[str, object]
) -> Optional[CanonicalPrincipal]:
    policy = settings.personal_connections
    if not policy.enabled or not policy.identity_namespace.strip():
        return None
    if settings.admin_authentication.mode == "disabled" or _machine_identity(claims):
        return None
    issuer = claims.get("iss")
    if "iss" in claims:
        if not isinstance(issuer, str) or not settings.oidc.issuer_url:
            return None
        if issuer != settings.oidc.issuer_url:
            return None
    elif settings.oidc.provider != "google":
        return None
    subject = _string_claim(claims, "sub")
    if settings.oidc.provider == "azure_entra_id":
        tenant = _string_claim(claims, "tid")
        if not tenant or tenant != settings.oidc.tenant_id:
            return None
        if not _string_claim(claims, "scp"):
            return None
        object_id = _string_claim(claims, "oid")
        if not object_id:
            return None
        subject = f"{tenant}:{object_id}"
    if not subject:
        return None
    return CanonicalPrincipal(namespace=policy.identity_namespace, subject=subject)


class VerifiedClaimsPrincipalProvider:
    def __init__(self, settings: AppConfig, claims: Mapping[str, object]) -> None:
        self._settings = settings
        self._claims = claims

    async def get_principal(self) -> Optional[CanonicalPrincipal]:
        return canonical_principal(self._settings, self._claims)
