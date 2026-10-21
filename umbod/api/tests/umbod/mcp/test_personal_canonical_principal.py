from collections.abc import Mapping
from typing import Literal

import pytest
from fastmcp.server.auth import AccessToken
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from umbod.config.app import (
    AdminAuthConfig,
    AppConfig,
    McpConfig,
    OidcConfig,
    PersonalConnectionsConfig,
    RuntimeConfig,
)
from umbod.core.connectors.downstream_mcp.personal_connections.ports import (
    CanonicalPrincipalProvider,
)
from umbod.core.connectors.downstream_mcp.personal_connections import VerifiedClaimsPrincipalProvider
from umbod.mcp.connectors.downstream_mcp.principal import McpCanonicalPrincipalProvider

pytestmark = pytest.mark.anyio

Provider = Literal["google", "auth0", "azure_entra_id"]


def _settings(
    provider: Provider = "google", namespace: str = "authority", tenant: str = "tenant"
) -> AppConfig:
    return AppConfig(
        runtime=RuntimeConfig(profile="production", auth=provider),
        admin_authentication=AdminAuthConfig(
            environment="production", mode="jwt", jwks_url="https://upstream/keys"
        ),
        mcp=McpConfig(auth_mode="oidc"),
        oidc=OidcConfig(
            provider=provider,
            issuer_url="https://upstream/",
            audience="api",
            tenant_id=tenant,
        ),
        personal_connections=PersonalConnectionsConfig(
            enabled=True, identity_namespace=namespace
        ),
    )


def _claims(provider: Provider) -> dict[str, object]:
    if provider == "azure_entra_id":
        return {
            "sub": "rest-app-subject",
            "oid": "object",
            "tid": "tenant",
            "scp": "access",
            "iss": "https://upstream/",
        }
    return {"sub": "account", "iss": "https://upstream/"}


@pytest.mark.parametrize("provider", ["google", "auth0", "azure_entra_id"])
async def test_verified_rest_and_upstream_mcp_claims_have_identical_ownership(
    provider: Provider,
) -> None:
    settings = _settings(provider)
    claims = _claims(provider)
    rest: CanonicalPrincipalProvider = VerifiedClaimsPrincipalProvider(settings, claims)
    mcp_claims = dict(claims)
    if provider == "azure_entra_id":
        mcp_claims["sub"] = "different-mcp-application-subject"
    if provider == "google":
        mcp_claims.pop("iss")
    token = AccessToken(
        token="opaque-outer-proxy-token",
        client_id="mcp-client",
        scopes=[],
        claims=mcp_claims,
    )
    context = auth_context_var.set(AuthenticatedUser(token))
    try:
        mcp: CanonicalPrincipalProvider = McpCanonicalPrincipalProvider(settings)
        assert await rest.get_principal() == await mcp.get_principal()
        assert await rest.get_principal() is not None
    finally:
        auth_context_var.reset(context)


@pytest.mark.parametrize("provider", ["google", "auth0", "azure_entra_id"])
async def test_separate_namespaces_do_not_share_ownership(provider: Provider) -> None:
    first: CanonicalPrincipalProvider = VerifiedClaimsPrincipalProvider(
        _settings(provider, "first"), _claims(provider)
    )
    second: CanonicalPrincipalProvider = VerifiedClaimsPrincipalProvider(
        _settings(provider, "second"), _claims(provider)
    )
    assert await first.get_principal() != await second.get_principal()


async def test_entra_tenants_do_not_share_object_ownership() -> None:
    first_claims = _claims("azure_entra_id")
    second_claims = {**first_claims, "tid": "other"}
    first: CanonicalPrincipalProvider = VerifiedClaimsPrincipalProvider(
        _settings("azure_entra_id"), first_claims
    )
    second: CanonicalPrincipalProvider = VerifiedClaimsPrincipalProvider(
        _settings("azure_entra_id", tenant="other"), second_claims
    )
    assert await first.get_principal() != await second.get_principal()


@pytest.mark.parametrize(
    "provider,claims",
    [
        ("google", {}),
        ("google", {"sub": 3}),
        ("google", {"sub": " "}),
        ("google", {"sub": {"id": "account"}}),
        ("google", {"email": "user@example.org", "client_id": "account"}),
        ("google", {"sub": "account", "iss": "https://outer-mcp/"}),
        ("google", {"sub": "account", "iss": 7}),
        ("google", {"sub": "account", "iss": None}),
        (
            "google",
            {"sub": "account", "email": "robot@project.iam.gserviceaccount.com"},
        ),
        ("auth0", {"sub": "account"}),
        ("auth0", {"sub": "machine@clients", "iss": "https://upstream/"}),
        (
            "auth0",
            {"sub": "account", "iss": "https://upstream/", "gty": "client-credentials"},
        ),
        (
            "azure_entra_id",
            {
                "oid": "object",
                "tid": "wrong",
                "scp": "read",
                "iss": "https://upstream/",
            },
        ),
        (
            "azure_entra_id",
            {"oid": "object", "tid": "tenant", "iss": "https://upstream/"},
        ),
        (
            "azure_entra_id",
            {
                "oid": "object",
                "tid": "tenant",
                "scp": "read",
                "idtyp": "app",
                "iss": "https://upstream/",
            },
        ),
        (
            "azure_entra_id",
            {
                "sub": "account",
                "tid": "tenant",
                "scp": "read",
                "iss": "https://upstream/",
            },
        ),
        (
            "azure_entra_id",
            {
                "oid": ["object"],
                "tid": "tenant",
                "scp": "read",
                "iss": "https://upstream/",
            },
        ),
    ],
)
async def test_invalid_or_machine_only_verified_claims_are_unmappable(
    provider: Provider, claims: Mapping[str, object]
) -> None:
    principal: CanonicalPrincipalProvider = VerifiedClaimsPrincipalProvider(
        _settings(provider), claims
    )
    assert await principal.get_principal() is None


async def test_disabled_policy_never_maps_claims() -> None:
    principal: CanonicalPrincipalProvider = VerifiedClaimsPrincipalProvider(
        AppConfig(), {"sub": "account"}
    )
    assert await principal.get_principal() is None


async def test_mcp_identity_is_read_from_current_context_without_caching() -> None:
    principal: CanonicalPrincipalProvider = McpCanonicalPrincipalProvider(_settings())
    context = auth_context_var.set(None)
    try:
        assert await principal.get_principal() is None
        token = AccessToken(
            token="opaque", client_id="client", scopes=[], claims={"sub": "first"}
        )
        auth_context_var.set(AuthenticatedUser(token))
        first = await principal.get_principal()
        token = AccessToken(
            token="opaque", client_id="client", scopes=[], claims={"sub": "second"}
        )
        auth_context_var.set(AuthenticatedUser(token))
        assert first != await principal.get_principal()
        auth_context_var.set(None)
        assert await principal.get_principal() is None
    finally:
        auth_context_var.reset(context)
