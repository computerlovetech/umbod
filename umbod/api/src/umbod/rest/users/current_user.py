from typing import Protocol

from fastapi import HTTPException, Request

from umbod.core.callers import CallerContext, SubjectIdentity
from umbod.rest.authentication import JwtClaims, JwtVerificationError, JwtVerifier
from umbod.rest.authentication.caller import (
    RestCallerContextProvider,
    authentication_provenance,
)
from umbod.rest.authentication.deps import (
    CALLER_CONTEXT_STATE_KEY,
    VERIFIED_ACCESS_CLAIMS_STATE_KEY,
    get_caller_context,
    get_verified_access_claims,
)
from umbod.rest.users.profiles import UserProfileInput, UserProfileProvider
from umbod.rest.authentication.tokens import extract_request_jwt_token
from umbod.rest.users.responses import CurrentUserResponse


class CurrentUserProvider(Protocol):
    def get_current_user(self, request: Request) -> CurrentUserResponse: ...


class JwtCurrentUserProvider:
    def __init__(
        self,
        jwt_header_name: str,
        jwt_verifier: JwtVerifier,
        profile_provider: UserProfileProvider,
        profile_header_name: str,
    ) -> None:
        self.jwt_header_name = jwt_header_name
        self.jwt_verifier = jwt_verifier
        self.profile_provider = profile_provider
        self.profile_header_name = profile_header_name

    def get_current_user(self, request: Request) -> CurrentUserResponse:
        if isinstance(
            getattr(request.state, VERIFIED_ACCESS_CLAIMS_STATE_KEY, None), JwtClaims
        ):
            jwt_claims = get_verified_access_claims(request)
        else:
            token = extract_request_jwt_token(request.headers, self.jwt_header_name)
            try:
                jwt_claims = self.jwt_verifier.verify(token)
            except JwtVerificationError as error:
                raise HTTPException(status_code=401, detail="Unauthorized") from error
        if isinstance(getattr(request.state, CALLER_CONTEXT_STATE_KEY, None), CallerContext):
            context = get_caller_context(request)
        else:
            context = RestCallerContextProvider(
                jwt_claims, authentication_provenance(self.jwt_verifier)
            ).get_context()
        if not isinstance(context.subject, SubjectIdentity):
            raise HTTPException(status_code=401, detail="Unauthorized")
        profile = self.profile_provider.get_profile(
            UserProfileInput(
                access_claims=jwt_claims,
                token=request.headers.get(self.profile_header_name, ""),
                header_present=self.profile_header_name in request.headers,
            )
        )
        return CurrentUserResponse(
            id=context.subject.subject,
            email=profile.email or None,
            name=profile.name,
            picture=profile.picture or None,
        )
