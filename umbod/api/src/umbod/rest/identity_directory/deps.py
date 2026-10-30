from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from umbod.core.callers import AuthenticationProvenance, CallerContext
from umbod.core.identity_directory.models import IdentityObservation
from umbod.core.identity_directory.ports import IdentityDirectoryStore
from umbod.core.identity_directory.service import IdentityObservationService
from umbod.core.identity_directory.store import DatabaseIdentityDirectory
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import (
    get_caller_context,
    get_verified_access_claims,
)
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.users.mapping import ClaimProfileMapper
from umbod.rest.users.deps import (
    get_profile_signing_key_resolver,
    get_user_profile_provider,
)
from umbod.rest.users.id_token import OidcIdTokenUserProfileProvider
from umbod.rest.users.profiles import UserProfileInput


async def get_identity_directory(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> IdentityDirectoryStore:
    await factories.persistence_runtime.readiness.ensure_ready()
    return DatabaseIdentityDirectory(factories.persistence_runtime.database)


def get_observation_service(
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> IdentityObservationService:
    return IdentityObservationService(
        DatabaseIdentityDirectory(factories.persistence_runtime.database)
    )


async def capture_observation(
    request: Request,
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    claims: Annotated[JwtClaims, Depends(get_verified_access_claims)],
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> Optional[IdentityObservation]:
    config = factories.settings
    if caller.authentication != AuthenticationProvenance.UPSTREAM_VERIFIED:
        if config.admin_authentication.mode != "jwt":
            return None
        raise HTTPException(status_code=401, detail="Unauthorized")
    issuer = claims.claims.get("iss")
    subject = claims.claims.get("sub")
    if (
        not config.oidc.issuer_url.strip()
        or issuer != config.oidc.issuer_url
        or not isinstance(subject, str)
        or not subject.strip()
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
    claim = config.mcp.permission_group_claim
    if not claim.strip():
        return None
    raw_groups = claims.claims.get(claim)
    values = (
        (raw_groups,)
        if isinstance(raw_groups, str)
        else raw_groups
        if isinstance(raw_groups, (list, tuple))
        else ()
    )
    profile_claims = claims
    if config.user_profile.mode == "id_token":
        try:
            resolver = get_profile_signing_key_resolver(config, request)
            provider = get_user_profile_provider(config, resolver)
            if isinstance(provider, OidcIdTokenUserProfileProvider):
                profile_claims = await run_in_threadpool(
                    provider.resolve_claims,
                    UserProfileInput(
                        access_claims=claims,
                        token=request.headers.get(
                            config.user_profile.jwt_header_name, ""
                        ),
                        header_present=config.user_profile.jwt_header_name
                        in request.headers,
                    ),
                )
        except Exception:
            profile_claims = claims
    profile_config = config.user_profile
    profile = ClaimProfileMapper(
        profile_config.name_claim,
        profile_config.email_claim,
        profile_config.picture_claim,
    ).map(profile_claims)
    raw_name = profile_claims.claims.get(profile_config.name_claim)
    verification = profile_claims.claims.get("email_verified")
    return IdentityObservation(
        issuer=issuer,
        subject=subject,
        claim=claim,
        groups=tuple(
            value for value in values if isinstance(value, str) and value.strip()
        ),
        name=profile.name if isinstance(raw_name, str) and raw_name.strip() else "",
        email=profile.email,
        email_verification="verified"
        if profile.email and verification is True
        else "unverified"
        if profile.email and verification is False
        else "unknown",
        observed_at=datetime.now(timezone.utc),
    )
