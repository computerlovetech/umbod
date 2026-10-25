from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from umbod.rest.authentication.authorization import JwtVerificationError, JwtVerifier
from umbod.rest.authentication.caller import (
    RestCallerContextProvider,
    authentication_provenance,
)
from umbod.rest.authentication.deps import (
    CALLER_CONTEXT_STATE_KEY,
    VERIFIED_ACCESS_CLAIMS_STATE_KEY,
)
from umbod.rest.authentication.tokens import extract_request_jwt_token
from umbod.rest.authentication.verifiers import SimulatedJwtVerifier


class UserAuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: ASGIApp, verifier: JwtVerifier, jwt_header_name: str,
        allow_missing_simulated_token: bool,
    ) -> None:
        super().__init__(app)
        self._verifier = verifier
        self._jwt_header_name = jwt_header_name
        self._allow_missing_simulated_token = (
            allow_missing_simulated_token and type(verifier) is SimulatedJwtVerifier
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        token = extract_request_jwt_token(request.headers, self._jwt_header_name)
        if not token and not self._allow_missing_simulated_token:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        try:
            claims = self._verifier.verify(token)
        except JwtVerificationError:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        context = RestCallerContextProvider(
            claims, authentication_provenance(self._verifier)
        ).get_context()
        setattr(request.state, VERIFIED_ACCESS_CLAIMS_STATE_KEY, claims)
        setattr(request.state, CALLER_CONTEXT_STATE_KEY, context)
        return await call_next(request)
