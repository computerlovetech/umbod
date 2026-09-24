from typing import Literal, Protocol

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from umbod.rest.authentication.authorization import (
    AdminAuthorizationPolicy,
    AdminAuthorizationService,
    JwtClaims,
    JwtVerificationError,
    JwtVerifier,
)
from umbod.rest.authentication.tokens import extract_jwt_header_token
from umbod.rest.authentication.verifiers import (
    ProductionJwksJwtVerifier,
    SemanticJwtVerifier,
    SimulatedJwtVerifier,
)


class AdminAuthenticationModeSettingsPort(Protocol):
    mode: Literal["disabled", "jwt", "simulation"]


class AdminJwtVerifierSettingsPort(AdminAuthenticationModeSettingsPort, Protocol):
    environment: Literal["development", "production"]
    jwks_url: str


class AdminAuthorizationPolicySettingsPort(Protocol):
    membership_claim: str
    required_membership: str


class AdminRequestAuthenticationSettingsPort(AdminAuthenticationModeSettingsPort, Protocol):
    debug_enabled: bool
    jwt_header_name: str
    simulated_admin: bool
    simulated_user_id: str
    simulated_user_email: str
    simulated_user_name: str


class AdminAuthenticationSettingsPort(
    AdminJwtVerifierSettingsPort,
    AdminAuthorizationPolicySettingsPort,
    AdminRequestAuthenticationSettingsPort,
    Protocol,
):
    pass


class APISettingsPort(Protocol):
    admin_authentication: AdminAuthenticationSettingsPort


class AdminAuthorizationServicePort(Protocol):
    def verify_claims(self, token: str) -> JwtClaims: ...

    def is_authorized(self, claims: JwtClaims) -> bool: ...


class AdminAuthorizationServiceFactoryPort(Protocol):
    def create(self, settings: APISettingsPort) -> AdminAuthorizationServicePort: ...


class AdminAuthenticationStrategy(Protocol):
    async def authenticate(self, request: Request) -> Response | None: ...


class JwtVerifierFactory:
    def create(self, settings: APISettingsPort) -> JwtVerifier:
        authentication_settings = settings.admin_authentication
        if authentication_settings.mode == "simulation":
            return SimulatedJwtVerifier(
                authentication_settings.simulated_user_id,
                authentication_settings.simulated_user_email,
                authentication_settings.simulated_user_name,
                authentication_settings.membership_claim,
                authentication_settings.required_membership,
                authentication_settings.simulated_admin,
            )
        if authentication_settings.environment == "production":
            return ProductionJwksJwtVerifier(authentication_settings.jwks_url)
        return SemanticJwtVerifier()


class AdminAuthorizationServiceFactory:
    def __init__(self, jwt_verifier_factory: JwtVerifierFactory) -> None:
        self.jwt_verifier_factory = jwt_verifier_factory

    def create(self, settings: APISettingsPort) -> AdminAuthorizationServicePort:
        authentication_settings = settings.admin_authentication
        return AdminAuthorizationService(
            self.jwt_verifier_factory.create(settings),
            AdminAuthorizationPolicy(
                membership_claim=authentication_settings.membership_claim,
                required_membership=authentication_settings.required_membership,
            ),
        )


class JwtAdminAuthenticationStrategy:
    def __init__(
        self, jwt_header_name: str, authorization_service: AdminAuthorizationServicePort
    ) -> None:
        self.jwt_header_name = jwt_header_name
        self.authorization_service = authorization_service

    async def authenticate(self, request: Request) -> Response | None:
        token = extract_jwt_header_token(request.headers.get(self.jwt_header_name, ""))
        try:
            claims = self.authorization_service.verify_claims(token)
        except JwtVerificationError:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        if not self.authorization_service.is_authorized(claims):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        return None


class AdminAuthenticationStrategyFactory:
    def __init__(self, authorization_service_factory: AdminAuthorizationServiceFactoryPort) -> None:
        self.authorization_service_factory = authorization_service_factory

    def create(self, settings: APISettingsPort) -> AdminAuthenticationStrategy:
        authentication_settings = settings.admin_authentication
        return JwtAdminAuthenticationStrategy(
            authentication_settings.jwt_header_name,
            self.authorization_service_factory.create(settings),
        )


class AdminAuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        strategy: AdminAuthenticationStrategy,
    ) -> None:
        super().__init__(app)
        self.strategy = strategy

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        authentication_response = await self.strategy.authenticate(request)
        if authentication_response is not None:
            return authentication_response
        return await call_next(request)
