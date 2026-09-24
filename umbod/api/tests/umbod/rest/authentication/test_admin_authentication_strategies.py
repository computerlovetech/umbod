from dataclasses import dataclass
from typing import Literal

import pytest
from fastapi import Request
from fastapi.responses import Response

from umbod.rest.authentication import JwtClaims, JwtVerificationError
from umbod.rest.authentication.middleware import (
    AdminAuthenticationStrategy,
    AdminAuthenticationStrategyFactory,
    AdminAuthorizationServicePort,
    APISettingsPort,
    JwtAdminAuthenticationStrategy,
    JwtVerifierFactory,
)
from umbod.rest.authentication.verifiers import (
    ProductionJwksJwtVerifier,
    SemanticJwtVerifier,
    SimulatedJwtVerifier,
)


@dataclass(frozen=True)
class AdminAuthenticationSettings:
    mode: Literal["jwt", "simulation"] = "jwt"
    environment: Literal["development", "production"] = "development"
    jwks_url: str = "https://identity.example.com/.well-known/jwks.json"
    membership_claim: str = "groups"
    required_membership: str = "admins"
    jwt_header_name: str = "X-Forwarded-Access-Token"
    simulated_admin: bool = True
    simulated_user_id: str = "sim-user"
    simulated_user_email: str = "sim@example.com"
    simulated_user_name: str = "Sim User"


@dataclass(frozen=True)
class APISettings:
    admin_authentication: AdminAuthenticationSettings


class FakeAuthorizationService:
    def __init__(self, authorized: bool, verification_error: bool) -> None:
        self.authorized = authorized
        self.verification_error = verification_error
        self.verified_token: str | None = None

    def verify_claims(self, token: str) -> JwtClaims:
        self.verified_token = token
        if self.verification_error:
            raise JwtVerificationError()
        return JwtClaims(claims={"groups": ["admins"]})

    def is_authorized(self, claims: JwtClaims) -> bool:
        return self.authorized


class FakeAuthorizationServiceFactory:
    def __init__(self, service: AdminAuthorizationServicePort) -> None:
        self.service = service

    def create(self, settings: APISettingsPort) -> AdminAuthorizationServicePort:
        return self.service


def _create_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = []
    for name, value in (headers or {}).items():
        raw_headers.append((name.lower().encode(), value.encode()))
    return Request({"type": "http", "method": "GET", "path": "/admin", "headers": raw_headers})


@pytest.mark.anyio
async def test_jwt_strategy_verifies_empty_token_when_header_is_missing() -> None:
    service = FakeAuthorizationService(False, False)
    strategy = JwtAdminAuthenticationStrategy("X-Forwarded-Access-Token", service)

    response = await strategy.authenticate(_create_request({"Authorization": "token"}))

    assert isinstance(response, Response)
    assert response.status_code == 403
    assert service.verified_token == ""


@pytest.mark.anyio
async def test_jwt_strategy_allows_authorized_claims() -> None:
    service = FakeAuthorizationService(True, False)
    strategy = JwtAdminAuthenticationStrategy("X-Forwarded-Access-Token", service)

    response = await strategy.authenticate(_create_request({"X-Forwarded-Access-Token": "token"}))

    assert response is None
    assert service.verified_token == "token"


@pytest.mark.anyio
async def test_jwt_strategy_rejects_invalid_token() -> None:
    strategy = JwtAdminAuthenticationStrategy(
        "X-Forwarded-Access-Token", FakeAuthorizationService(True, True)
    )

    response = await strategy.authenticate(_create_request({"X-Forwarded-Access-Token": "token"}))

    assert isinstance(response, Response)
    assert response.status_code == 401


@pytest.mark.anyio
async def test_jwt_strategy_forbids_unauthorized_claims() -> None:
    strategy = JwtAdminAuthenticationStrategy(
        "X-Forwarded-Access-Token", FakeAuthorizationService(False, False)
    )

    response = await strategy.authenticate(_create_request({"X-Forwarded-Access-Token": "token"}))

    assert isinstance(response, Response)
    assert response.status_code == 403


def test_strategy_factory_returns_jwt_strategy_for_simulation_mode() -> None:
    settings = APISettings(AdminAuthenticationSettings(mode="simulation", simulated_admin=True))

    strategy = AdminAuthenticationStrategyFactory(
        FakeAuthorizationServiceFactory(FakeAuthorizationService(True, False))
    ).create(settings)

    assert isinstance(strategy, JwtAdminAuthenticationStrategy)


def test_strategy_factory_selects_jwt_strategy_for_jwt_mode() -> None:
    service = FakeAuthorizationService(True, False)
    settings = APISettings(AdminAuthenticationSettings(mode="jwt"))

    strategy = AdminAuthenticationStrategyFactory(FakeAuthorizationServiceFactory(service)).create(
        settings
    )

    assert isinstance(strategy, JwtAdminAuthenticationStrategy)


def test_strategy_factory_returns_protocol_compatible_strategy() -> None:
    settings = APISettings(AdminAuthenticationSettings(mode="simulation"))

    strategy: AdminAuthenticationStrategy = AdminAuthenticationStrategyFactory(
        FakeAuthorizationServiceFactory(FakeAuthorizationService(True, False)),
    ).create(settings)

    assert isinstance(strategy, JwtAdminAuthenticationStrategy)


def test_jwt_verifier_factory_uses_simulated_verifier_for_simulation() -> None:
    settings = APISettings(AdminAuthenticationSettings(mode="simulation"))

    verifier = JwtVerifierFactory().create(settings)

    assert isinstance(verifier, SimulatedJwtVerifier)


def test_jwt_verifier_factory_uses_semantic_verifier_outside_production() -> None:
    settings = APISettings(AdminAuthenticationSettings(mode="jwt", environment="development"))

    verifier = JwtVerifierFactory().create(settings)

    assert isinstance(verifier, SemanticJwtVerifier)


def test_jwt_verifier_factory_uses_jwks_verifier_in_production() -> None:
    settings = APISettings(AdminAuthenticationSettings(mode="jwt", environment="production"))

    verifier = JwtVerifierFactory().create(settings)

    assert isinstance(verifier, ProductionJwksJwtVerifier)
