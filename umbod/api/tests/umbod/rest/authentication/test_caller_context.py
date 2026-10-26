from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from umbod.config import AppConfig
from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
    UnavailableIssuer,
    UnavailableSubject,
)
from umbod.rest.authentication.authorization import (
    AdminAuthorizationPolicy,
    AdminAuthorizationService,
    JwtClaims,
    JwtVerificationError,
    JwtVerifier,
)
from umbod.rest.authentication.caller import caller_context_from_claims
from umbod.rest.authentication.deps import CALLER_CONTEXT_STATE_KEY, get_caller_context
from umbod.rest.authentication.middleware import JwtAdminAuthenticationStrategy, SuppliedJwtVerifierFactory
from umbod.rest.authentication.rest_middleware import RestAuthenticationMiddleware
from umbod.rest.authentication.verifiers import (
    ProductionJwksJwtVerifier,
    SemanticJwtVerifier,
    SimulatedJwtVerifier,
)
from umbod.rest.users.current_user import CurrentUserProvider, JwtCurrentUserProvider
from umbod.rest.users.mapping import AccessClaimsUserProfileProvider, ClaimProfileMapper


@pytest.mark.parametrize("subject,issuer", [("", ""), (" User / A ", "https://issuer/ ")])
def test_capture_preserves_exact_identity(subject: str, issuer: str) -> None:
    context = caller_context_from_claims(
        JwtClaims(claims={"sub": subject, "iss": issuer}),
        AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
    )

    assert context.subject == SubjectIdentity(
        issuer=DeclaredIssuer(value=issuer), subject=subject
    )


@pytest.mark.parametrize("claims", [{}, {"sub": None}, {"sub": 42}, {"sub": []}])
def test_capture_models_unavailable_subject(claims: dict[str, object]) -> None:
    context = caller_context_from_claims(
        JwtClaims(claims=claims), AuthenticationProvenance.LOCAL_TEST
    )

    assert context.subject == UnavailableSubject(kind="unavailable")


@pytest.mark.parametrize("claims", [{"sub": "u"}, {"sub": "u", "iss": None}, {"sub": "u", "iss": 42}])
def test_capture_models_unavailable_issuer(claims: dict[str, object]) -> None:
    context = caller_context_from_claims(
        JwtClaims(claims=claims), AuthenticationProvenance.LOCAL_TEST
    )

    assert context.subject == SubjectIdentity(
        issuer=UnavailableIssuer(kind="unavailable"), subject="u"
    )


def test_context_is_an_immutable_snapshot_of_verified_claims() -> None:
    claims = JwtClaims(claims={"sub": "original", "iss": "issuer"})
    context = caller_context_from_claims(
        claims, AuthenticationProvenance.LOCAL_TEST
    )
    claims.claims.update(sub="changed", iss="changed")

    assert context.subject == SubjectIdentity(
        issuer=DeclaredIssuer(value="issuer"), subject="original"
    )
    with pytest.raises(ValidationError):
        context.authentication = AuthenticationProvenance.UNAVAILABLE


def test_missing_request_context_is_unauthorized() -> None:
    request = Request({"type": "http", "headers": []})

    with pytest.raises(HTTPException) as error:
        get_caller_context(request)

    assert error.value.status_code == 401


def _user_client(verifier: JwtVerifier) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RestAuthenticationMiddleware,
        settings=AppConfig(),
        admin_verifier_factory=SuppliedJwtVerifierFactory(verifier),
        user_verifier_factory=SuppliedJwtVerifierFactory(verifier),
    )

    @app.get("/api/me/probe")
    def caller(request: Request) -> CallerContext:
        return get_caller_context(request)

    return TestClient(app)


@pytest.mark.parametrize(
    "verifier,expected",
    [
        (ProductionJwksJwtVerifier("https://issuer/keys", "issuer", "audience"), AuthenticationProvenance.UPSTREAM_VERIFIED),
        (SimulatedJwtVerifier("u", "e", "n", "groups", "admins", True), AuthenticationProvenance.LOCAL_SIMULATION),
        (SemanticJwtVerifier(), AuthenticationProvenance.LOCAL_SEMANTIC),
        (Mock(spec=JwtVerifier), AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED),
    ],
)
def test_user_http_context_provenance_uses_actual_verifier(
    verifier: JwtVerifier, expected: AuthenticationProvenance, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(verifier, "verify", Mock(return_value=JwtClaims(claims={
        "sub": "u", "iss": "issuer", "authentication": "upstream_verified"
    })))

    with _user_client(verifier) as client:
        response = client.get("/api/me/probe", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    assert response.json()["authentication"] == expected.value


@pytest.mark.parametrize("authorized,invalid", [(False, False), (True, True)])
@pytest.mark.anyio
async def test_failed_admin_authentication_does_not_store_context(
    authorized: bool, invalid: bool
) -> None:
    service = Mock()
    service.is_authorized.return_value = authorized
    service.verify_claims.return_value = JwtClaims(claims={"sub": "u"})
    if invalid:
        service.verify_claims.side_effect = JwtVerificationError()
    strategy = JwtAdminAuthenticationStrategy("Authorization", service)
    request = Request({"type": "http", "headers": [(b"authorization", b"Bearer token")]})

    response = await strategy.authenticate(request)

    assert response is not None
    assert response.status_code == (401 if invalid else 403)
    assert not hasattr(request.state, CALLER_CONTEXT_STATE_KEY)


@pytest.mark.parametrize("missing_token", [True, False])
@pytest.mark.anyio
async def test_failed_user_authentication_does_not_store_context(missing_token: bool) -> None:
    verifier = Mock(spec=JwtVerifier)
    verifier.verify.side_effect = JwtVerificationError()
    middleware = RestAuthenticationMiddleware(
        FastAPI(), AppConfig(), SuppliedJwtVerifierFactory(verifier), SuppliedJwtVerifierFactory(verifier),
    )
    request = Request({
        "type": "http",
        "path": "/api/me/probe", "method": "GET",
        "headers": [] if missing_token else [(b"authorization", b"Bearer token")],
    })
    call_next = AsyncMock()

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 401
    assert not hasattr(request.state, CALLER_CONTEXT_STATE_KEY)
    call_next.assert_not_called()


@pytest.mark.parametrize("concrete", [True, False])
@pytest.mark.anyio
async def test_admin_context_uses_concrete_verifier_or_deployment_hook(concrete: bool) -> None:
    verifier = SemanticJwtVerifier()
    claims = JwtClaims(claims={"sub": "u", "groups": ["admins"]})
    service = AdminAuthorizationService(
        verifier, AdminAuthorizationPolicy(membership_claim="groups", required_membership="admins")
    ) if concrete else Mock()
    if not concrete:
        service.verify_claims.return_value = claims
        service.is_authorized.return_value = True
    token = '{"signature":"trusted","claims":{"sub":"u","groups":["admins"]}}'
    request = Request({"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]})

    assert await JwtAdminAuthenticationStrategy("Authorization", service).authenticate(request) is None
    assert get_caller_context(request).authentication == (
        AuthenticationProvenance.LOCAL_SEMANTIC if concrete
        else AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED
    )


def test_current_user_fallback_verifies_and_accepts_empty_subject() -> None:
    verifier = Mock(spec=JwtVerifier)
    verifier.verify.return_value = JwtClaims(claims={"sub": ""})
    provider: CurrentUserProvider = JwtCurrentUserProvider(
        "Authorization", verifier,
        AccessClaimsUserProfileProvider(ClaimProfileMapper("name", "email", "picture")),
        "X-Profile",
    )
    request = Request({"type": "http", "headers": []})

    assert provider.get_current_user(request).id == ""
    verifier.verify.assert_called_once_with("")


@pytest.mark.parametrize("subject", ["", "original"])
def test_current_user_reuses_context_subject_without_reverification(subject: str) -> None:
    verifier = Mock(spec=JwtVerifier)
    claims = JwtClaims(claims={"sub": subject, "email": "profile@example.com"})
    verifier.verify.return_value = claims
    provider: CurrentUserProvider = JwtCurrentUserProvider(
        "Authorization", verifier,
        AccessClaimsUserProfileProvider(ClaimProfileMapper("name", "email", "picture")),
        "X-Profile",
    )
    app = FastAPI()
    app.add_middleware(
        RestAuthenticationMiddleware, settings=AppConfig(),
        admin_verifier_factory=SuppliedJwtVerifierFactory(verifier),
        user_verifier_factory=SuppliedJwtVerifierFactory(verifier),
    )

    @app.get("/api/me/probe")
    def user(request: Request) -> dict[str, object]:
        claims.claims["sub"] = "mutated"
        return provider.get_current_user(request).model_dump()

    with TestClient(app) as client:
        response = client.get("/api/me/probe", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    assert response.json()["id"] == subject
    assert response.json()["email"] == "profile@example.com"
    verifier.verify.assert_called_once_with("token")
