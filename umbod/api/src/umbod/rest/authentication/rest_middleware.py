from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette._utils import get_route_path
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from umbod.config import AppConfig
from umbod.rest.authentication.authorization import JwtClaims, JwtVerificationError, JwtVerifier
from umbod.rest.authentication.caller import authentication_provenance, caller_context_from_claims
from umbod.rest.authentication.deps import CALLER_CONTEXT_STATE_KEY, VERIFIED_ACCESS_CLAIMS_STATE_KEY
from umbod.rest.authentication.local import LOCAL_DEVELOPMENT_ISSUER, local_rest_identity_enabled
from umbod.rest.authentication.middleware import JwtVerifierFactory
from umbod.rest.authentication.tokens import extract_request_jwt_token
from umbod.rest.authentication.verifiers import SimulatedJwtVerifier
from umbod.rest.authentication.rest_paths import protected_rest_request, within_namespace


class RestAuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app: ASGIApp, settings: AppConfig,
        admin_verifier_factory: JwtVerifierFactory,
        user_verifier_factory: JwtVerifierFactory,
    ) -> None:
        super().__init__(app)
        self._settings = settings
        default_factory = JwtVerifierFactory()
        self._default = default_factory.create(settings)
        self._admin = admin_verifier_factory.create(settings)
        self._user = user_verifier_factory.create(settings)
        self._local = local_rest_identity_enabled(settings)
        self._default_simulation = {
            "default": True,
            "admin": type(admin_verifier_factory) is JwtVerifierFactory,
            "user": type(user_verifier_factory) is JwtVerifierFactory,
        }

    def _selection(self, path: str) -> tuple[str, JwtVerifier]:
        if within_namespace(path, "/api/admin"):
            return "admin", self._admin
        if within_namespace(path, "/api/me"):
            return "user", self._user
        return "default", self._default

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = get_route_path(request.scope)
        if (
            (
                self._settings.admin_authentication.mode == "disabled"
                and within_namespace(path, "/api/admin")
            )
            or (
                request.method == "OPTIONS"
                and "origin" in request.headers
                and "access-control-request-method" in request.headers
            )
            or not protected_rest_request(request.scope)
        ):
            return await call_next(request)
        selection, verifier = self._selection(path)
        token = extract_request_jwt_token(
            request.headers, self._settings.admin_authentication.jwt_header_name,
        )
        default_simulation = self._default_simulation[selection] and type(verifier) is SimulatedJwtVerifier
        if (
            not token and selection != "admin" and not (self._local and default_simulation)
        ) or (default_simulation and not self._local):
            return self._unauthorized()
        try:
            claims = verifier.verify(token)
        except JwtVerificationError:
            return self._unauthorized()
        if self._local and default_simulation:
            claims = JwtClaims(claims={**claims.claims, "iss": LOCAL_DEVELOPMENT_ISSUER})
        setattr(request.state, VERIFIED_ACCESS_CLAIMS_STATE_KEY, claims)
        setattr(request.state, CALLER_CONTEXT_STATE_KEY, caller_context_from_claims(
            claims, authentication_provenance(verifier),
        ))
        response = await call_next(request)
        if response.status_code in (401, 403):
            response.headers["Cache-Control"] = "no-store"
        return response

    def _unauthorized(self) -> JSONResponse:
        return JSONResponse(
            status_code=401, content={"detail": "Unauthorized"},
            headers={"Cache-Control": "no-store"},
        )
