from collections.abc import Mapping
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentFastMCP
from fastmcp.server.auth.providers.auth0 import Auth0Provider
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)
from umbod.mcp.auth.local_test_auth import SingleTestUserOAuthProvider


def caller_context_from_access_token(
    token: object, authentication: AuthenticationProvenance,
) -> CallerContext:
    if token is None or authentication == AuthenticationProvenance.UNAVAILABLE:
        return CallerContext(
            authentication=AuthenticationProvenance.UNAVAILABLE,
            subject=UnavailableSubject(kind="unavailable"),
        )
    observed_claims = getattr(token, "claims", {})
    claims = observed_claims if isinstance(observed_claims, Mapping) else {}
    subject = claims.get("sub")
    issuer = claims.get("iss")
    return CallerContext(
        authentication=authentication,
        subject=SubjectIdentity(
            issuer=DeclaredIssuer(value=issuer)
            if isinstance(issuer, str)
            else UnavailableIssuer(kind="unavailable"),
            subject=subject,
        )
        if isinstance(subject, str)
        else UnavailableSubject(kind="unavailable"),
    )


def authentication_provenance(provider: object) -> AuthenticationProvenance:
    if type(provider) is SingleTestUserOAuthProvider:
        return AuthenticationProvenance.LOCAL_TEST
    if type(provider) in {GoogleProvider, AzureProvider, Auth0Provider}:
        return AuthenticationProvenance.UPSTREAM_VERIFIED
    return AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED


def get_caller_context(server: Annotated[FastMCP, CurrentFastMCP()]) -> CallerContext:
    provider = server.auth
    authentication = (
        authentication_provenance(provider)
        if provider is not None
        else AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
    )
    return caller_context_from_access_token(get_access_token(), authentication)
