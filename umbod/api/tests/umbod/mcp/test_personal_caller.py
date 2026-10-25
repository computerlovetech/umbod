from collections.abc import Mapping
from typing import Literal, Optional

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
from umbod.core.connectors.downstream_mcp.personal_connections import CanonicalPrincipal, PersonalCaller, UnavailablePersonalCaller, ResolvedPersonalIdentity
from umbod.core.connectors.downstream_mcp.personal_connections.principal import canonical_principal
from umbod.core.connectors.downstream_mcp.adapters.identity import personal_identity_facts
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
from umbod.mcp.connectors.downstream_mcp.personal_runtime import McpPersonalCallerProvider
from umbod.core.connectors.downstream_mcp.adapters.identity import authenticated_personal_mcp_claims
from umbod.rest.authentication.middleware import JwtVerifierFactory

pytestmark = pytest.mark.anyio

Provider = Literal["google", "auth0", "azure_entra_id"]


def _resolved_principal(settings: AppConfig, claims: Mapping[str, object]) -> Optional[CanonicalPrincipal]:
    resolution = canonical_principal(personal_identity_policy_from_app_config(settings), personal_identity_facts(claims))
    return resolution.principal if isinstance(resolution, ResolvedPersonalIdentity) else None


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
    rest: Optional[CanonicalPrincipal] = _resolved_principal(settings, claims)
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
        mcp = await McpPersonalCallerProvider(settings).get_caller()
        assert isinstance(mcp, PersonalCaller)
        assert rest == mcp.principal
        assert rest is not None
    finally:
        auth_context_var.reset(context)


@pytest.mark.parametrize("provider", ["google", "auth0", "azure_entra_id"])
async def test_separate_namespaces_do_not_share_ownership(provider: Provider) -> None:
    first: Optional[CanonicalPrincipal] = _resolved_principal(
        _settings(provider, "first"), _claims(provider)
    )
    second: Optional[CanonicalPrincipal] = _resolved_principal(
        _settings(provider, "second"), _claims(provider)
    )
    assert first != second


async def test_entra_tenants_do_not_share_object_ownership() -> None:
    first_claims = _claims("azure_entra_id")
    second_claims = {**first_claims, "tid": "other"}
    first: Optional[CanonicalPrincipal] = _resolved_principal(
        _settings("azure_entra_id"), first_claims
    )
    second: Optional[CanonicalPrincipal] = _resolved_principal(
        _settings("azure_entra_id", tenant="other"), second_claims
    )
    assert first != second


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
    principal: Optional[CanonicalPrincipal] = _resolved_principal(
        _settings(provider), claims
    )
    assert principal is None



def _local_settings(simulated_admin: bool = True, permission_group_claim: str = "custom-groups") -> AppConfig:
    return AppConfig(
        admin_authentication={
            "simulated_user_id": "stable-configured-user",
            "simulated_user_email": "configured@example.org",
            "simulated_user_name": "Configured Test User",
            "membership_claim": "custom-groups",
            "required_membership": "configured-admins",
            "simulated_admin": simulated_admin,
        },
        mcp={"auth_mode": "single_test_user", "permission_group_claim": permission_group_claim},
        personal_connections={"enabled": True, "identity_namespace": "test:local"},
    )


@pytest.mark.parametrize("simulated_admin,group_claim,expected_groups", [
    (True, "custom-groups", ("configured-admins",)),
    (False, "custom-groups", ()),
    (True, "different-groups", ()),
])
async def test_authenticated_local_mcp_matches_rest_without_mutating_global_claims(
    simulated_admin: bool, group_claim: str, expected_groups: tuple[str, ...],
) -> None:
    settings = _local_settings(simulated_admin, group_claim)
    rest_claims = JwtVerifierFactory().create(settings).verify("").claims
    claims = {"sub": "local-test-user", "groups": ["test"], "email": "original@example.org"}
    token = AccessToken(token="authenticated", client_id="client", scopes=[], claims=claims)
    context = auth_context_var.set(AuthenticatedUser(token))
    try:
        assert authenticated_personal_mcp_claims(settings, personal_identity_policy_from_app_config(settings), claims) == rest_claims
        rest = _resolved_principal(settings, rest_claims)
        runtime = await McpPersonalCallerProvider(settings).get_caller()
        assert isinstance(runtime, PersonalCaller)
        assert runtime.principal == rest
        assert runtime.groups.group_ids == expected_groups
        assert token.claims == claims
        assert token.claims["sub"] == "local-test-user"
    finally:
        auth_context_var.reset(context)


@pytest.mark.parametrize("claims", [
    {},
    {"sub": ""},
    {"sub": " "},
    {"sub": "different-user"},
    {"sub": "stable-configured-user", "iss": ""},
    {"sub": "stable-configured-user", "iss": "https://upstream/"},
    {"sub": "stable-configured-user", "iss": None},
    {"sub": "stable-configured-user", "idtyp": "app"},
    {"sub": "stable-configured-user", "email": "robot@project.iam.gserviceaccount.com"},
])
async def test_simulated_canonical_branch_rejects_untrusted_claims(claims: Mapping[str, object]) -> None:
    assert _resolved_principal(_local_settings(), claims) is None


@pytest.mark.parametrize("claims", [
    {"sub": "machine@clients"},
    {"sub": "local-test-user", "email": "robot@project.iam.gserviceaccount.com"},
    {"sub": "local-test-user", "idtyp": "app"},
    {"sub": "local-test-user", "gty": "client-credentials"},
    {"sub": "local-test-user", "grant_type": "client_credentials"},
])
async def test_local_mcp_rejects_original_machine_claims_before_normalization(claims: dict[str, object]) -> None:
    token = AccessToken(token="authenticated", client_id="client", scopes=[], claims=claims)
    context = auth_context_var.set(AuthenticatedUser(token))
    try:
        assert isinstance(await McpPersonalCallerProvider(_local_settings()).get_caller(), UnavailablePersonalCaller)
    finally:
        auth_context_var.reset(context)


async def test_local_personal_mcp_still_requires_current_authenticated_context() -> None:
    context = auth_context_var.set(None)
    try:
        assert isinstance(await McpPersonalCallerProvider(_local_settings()).get_caller(), UnavailablePersonalCaller)
    finally:
        auth_context_var.reset(context)


async def test_local_mcp_normalization_requires_single_test_user_authentication() -> None:
    settings = _local_settings()
    settings = settings.model_copy(update={"mcp": settings.mcp.model_copy(update={"auth_mode": "oidc"})})
    claims = {"sub": "original-subject", "groups": ["original"]}
    assert authenticated_personal_mcp_claims(settings, personal_identity_policy_from_app_config(settings), claims) == claims
    assert authenticated_personal_mcp_claims(_settings(), personal_identity_policy_from_app_config(_settings()), claims) == claims


async def test_disabled_policy_never_maps_claims() -> None:
    principal: Optional[CanonicalPrincipal] = _resolved_principal(
        AppConfig(), {"sub": "account"}
    )
    assert principal is None


async def test_mcp_identity_is_read_from_current_context_without_caching() -> None:
    provider = McpPersonalCallerProvider(_settings())
    context = auth_context_var.set(None)
    try:
        assert isinstance(await provider.get_caller(), UnavailablePersonalCaller)
        token = AccessToken(
            token="opaque", client_id="client", scopes=[], claims={"sub": "first"}
        )
        auth_context_var.set(AuthenticatedUser(token))
        first = await provider.get_caller()
        token = AccessToken(
            token="opaque", client_id="client", scopes=[], claims={"sub": "second"}
        )
        auth_context_var.set(AuthenticatedUser(token))
        assert first != await provider.get_caller()
        auth_context_var.set(None)
        assert isinstance(await provider.get_caller(), UnavailablePersonalCaller)
    finally:
        auth_context_var.reset(context)
