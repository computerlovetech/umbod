from collections.abc import Callable, Mapping
from typing import Annotated, Optional

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentFastMCP
from fastmcp.server.auth import AccessToken, AuthProvider
from fastmcp.server.auth.providers.auth0 import Auth0Provider
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token

from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    CallerContextProvider,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)
from umbod.mcp.auth.local_test_auth import SingleTestUserOAuthProvider


class McpCallerContextProvider:
    def __init__(
        self,
        token_reader: Callable[[], Optional[AccessToken]],
        authentication: AuthenticationProvenance,
    ) -> None:
        self._token_reader = token_reader
        self._authentication = authentication

    def get_context(self) -> CallerContext:
        token = self._token_reader()
        if token is None or self._authentication == AuthenticationProvenance.UNAVAILABLE:
            return CallerContext(
                authentication=AuthenticationProvenance.UNAVAILABLE,
                subject=UnavailableSubject(kind="unavailable"),
            )
        claims = token.claims if isinstance(token.claims, Mapping) else {}
        subject = claims.get("sub")
        issuer = claims.get("iss")
        return CallerContext(
            authentication=self._authentication,
            subject=SubjectIdentity(
                issuer=DeclaredIssuer(value=issuer)
                if isinstance(issuer, str)
                else UnavailableIssuer(kind="unavailable"),
                subject=subject,
            )
            if isinstance(subject, str)
            else UnavailableSubject(kind="unavailable"),
        )


def authentication_provenance(provider: AuthProvider) -> AuthenticationProvenance:
    if type(provider) is SingleTestUserOAuthProvider:
        return AuthenticationProvenance.LOCAL_TEST
    if type(provider) in {GoogleProvider, AzureProvider, Auth0Provider}:
        return AuthenticationProvenance.UPSTREAM_VERIFIED
    return AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED


def caller_context_provider(server: FastMCP) -> CallerContextProvider:
    provider = server.auth
    authentication = (
        authentication_provenance(provider)
        if provider is not None
        else AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
    )
    return McpCallerContextProvider(get_access_token, authentication)


def get_caller_context(server: Annotated[FastMCP, CurrentFastMCP()]) -> CallerContext:
    return caller_context_provider(server).get_context()
