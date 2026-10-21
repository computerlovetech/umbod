from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from umbod.rest.authentication.authorization import JwtVerificationError, JwtVerifier
from umbod.rest.authentication.deps import VERIFIED_ACCESS_CLAIMS_STATE_KEY
from umbod.rest.authentication.tokens import extract_request_jwt_token


class UserAuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, verifier: JwtVerifier, jwt_header_name: str) -> None:
        super().__init__(app)
        self._verifier = verifier
        self._jwt_header_name = jwt_header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        token = extract_request_jwt_token(request.headers, self._jwt_header_name)
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        try:
            claims = self._verifier.verify(token)
        except JwtVerificationError:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        setattr(request.state, VERIFIED_ACCESS_CLAIMS_STATE_KEY, claims)
        return await call_next(request)
