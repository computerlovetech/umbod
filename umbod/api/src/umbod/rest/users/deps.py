from typing import Annotated

from fastapi import Depends, Request

from umbod.config import AppConfig
from umbod.rest.authentication.middleware import JwtVerifierFactory
from umbod.rest.instance_configuration.dependencies import get_app_config
from umbod.rest.users.current_user import CurrentUserProvider, JwtCurrentUserProvider
from umbod.rest.users.id_token import (
    OidcIdTokenUserProfileProvider,
    OidcProfileJwtVerifier,
)
from umbod.rest.users.mapping import AccessClaimsUserProfileProvider, ClaimProfileMapper
from umbod.rest.users.profiles import UserProfileProvider
from umbod.rest.users.jwks import (
    CachedSigningKeyResolver,
    DisabledSigningKeyResolver,
    JwksProfileJwtVerifier,
)
from umbod.rest.users.signing_keys import SigningKeyResolver


def get_profile_signing_key_resolver(
    config: Annotated[AppConfig, Depends(get_app_config)],
    request: Request,
) -> SigningKeyResolver:
    if config.user_profile.mode == "access_claims":
        return DisabledSigningKeyResolver()
    resolver = getattr(request.state, "profile_signing_key_resolver", None)
    if not isinstance(resolver, CachedSigningKeyResolver):
        raise RuntimeError("Root lifespan profile signing-key resolver is not running")
    return resolver


def get_user_profile_provider(
    config: Annotated[AppConfig, Depends(get_app_config)],
    resolver: Annotated[SigningKeyResolver, Depends(get_profile_signing_key_resolver)],
) -> UserProfileProvider:
    profile = config.user_profile
    mapper = ClaimProfileMapper(
        profile.name_claim, profile.email_claim, profile.picture_claim
    )
    fallback = AccessClaimsUserProfileProvider(mapper)
    if profile.mode == "access_claims":
        return fallback
    verifier = OidcProfileJwtVerifier(
        JwksProfileJwtVerifier(resolver, config.oidc.issuer_url, config.oidc.client_id),
        config.oidc.client_id,
    )
    return OidcIdTokenUserProfileProvider(verifier, mapper, fallback)


def get_current_user_provider(
    config: Annotated[AppConfig, Depends(get_app_config)],
    profile_provider: Annotated[
        UserProfileProvider, Depends(get_user_profile_provider)
    ],
) -> CurrentUserProvider:
    return JwtCurrentUserProvider(
        config.admin_authentication.jwt_header_name,
        JwtVerifierFactory().create(config),
        profile_provider,
        config.user_profile.jwt_header_name,
    )
