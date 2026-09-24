from typing import Protocol

from fastapi import HTTPException, Request

from umbod.rest.authentication import JwtVerificationError, JwtVerifier
from umbod.rest.authentication.tokens import extract_jwt_header_token
from umbod.rest.users.responses import CurrentUserResponse


class CurrentUserProvider(Protocol):
    def get_current_user(self, request: Request) -> CurrentUserResponse: ...


class JwtCurrentUserProvider:
    def __init__(self, jwt_header_name: str, jwt_verifier: JwtVerifier) -> None:
        self.jwt_header_name = jwt_header_name
        self.jwt_verifier = jwt_verifier

    def get_current_user(self, request: Request) -> CurrentUserResponse:
        token = extract_jwt_header_token(request.headers.get(self.jwt_header_name, ""))
        try:
            jwt_claims = self.jwt_verifier.verify(token)
        except JwtVerificationError as error:
            raise HTTPException(status_code=401, detail="Unauthorized") from error
        user_id = jwt_claims.claims.get("sub")
        email = jwt_claims.claims.get("email")
        name = jwt_claims.claims.get("name", "unknown")
        picture = jwt_claims.claims.get("picture")
        if not isinstance(user_id, str) or not isinstance(email, str):
            raise HTTPException(status_code=401, detail="Unauthorized")
        if not isinstance(name, str):
            name = "unknown"
        if not isinstance(picture, str):
            picture = None
        return CurrentUserResponse(id=user_id, email=email, name=name, picture=picture)
