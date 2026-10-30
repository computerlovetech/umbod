from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from tests.support.identity_directory import InMemoryIdentityDirectory
from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
)
from umbod.core.identity_directory.models import IdentityObservation
from umbod.core.identity_directory.service import IdentityObservationService
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import (
    get_caller_context,
    get_verified_access_claims,
)
from umbod.rest.identity_directory.deps import get_observation_service
from umbod.rest.users.id_token import OidcIdTokenUserProfileProvider


def personal_app(client: TestClient) -> FastAPI:
    for route in client.app.routes:
        if isinstance(route, Mount) and route.path == "/api/me":
            assert isinstance(route.app, FastAPI)
            return route.app
    raise AssertionError("Personal app not mounted")


def verified_caller() -> CallerContext:
    return CallerContext(
        authentication=AuthenticationProvenance.UPSTREAM_VERIFIED,
        subject=SubjectIdentity(
            issuer=DeclaredIssuer(value="https://identity.example.com/"),
            subject="subject",
        ),
    )


def test_snapshot_does_not_retain_mutable_claims_or_request(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    raw: dict[str, object] = {
        "iss": "https://identity.example.com/",
        "sub": "subject",
        "permissions": ["original"],
        "name": "Original",
        "email": "original@example.test",
    }
    captured: list[IdentityObservation] = []

    def claims() -> JwtClaims:
        return JwtClaims(claims=raw)

    class RecordingService(IdentityObservationService):
        async def observe_best_effort(self, observation: IdentityObservation) -> None:
            cast(list[str], raw["permissions"]).append("injected")
            raw["name"] = "Changed"
            raw["email"] = "changed@example.test"
            captured.append(observation)

    def service() -> IdentityObservationService:
        return RecordingService(InMemoryIdentityDirectory())

    app = personal_app(client)
    app.dependency_overrides[get_verified_access_claims] = claims
    app.dependency_overrides[get_caller_context] = verified_caller
    app.dependency_overrides[get_observation_service] = service
    assert (
        client.post("/api/me/identity-observations", headers=auth_headers).status_code
        == 204
    )
    assert len(captured) == 1
    assert captured[0].groups == ("original",)
    assert captured[0].name == "Original"
    assert captured[0].email == "original@example.test"
    assert set(captured[0].model_dump()) == {
        "issuer",
        "subject",
        "claim",
        "groups",
        "name",
        "email",
        "email_verification",
        "observed_at",
    }


def test_optional_profile_resolution_failure_still_captures_groups(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def claims() -> JwtClaims:
        return JwtClaims(
            claims={
                "iss": "https://identity.example.com/",
                "sub": "subject",
                "permissions": ["access"],
                "name": "Access",
            }
        )

    def unavailable(
        self: OidcIdTokenUserProfileProvider, profile_input: object
    ) -> JwtClaims:
        raise RuntimeError("private-profile-payload")

    monkeypatch.setattr(OidcIdTokenUserProfileProvider, "resolve_claims", unavailable)
    app = personal_app(client)
    app.dependency_overrides[get_verified_access_claims] = claims
    app.dependency_overrides[get_caller_context] = verified_caller
    assert (
        client.post("/api/me/identity-observations", headers=auth_headers).status_code
        == 204
    )
    groups = client.get(
        "/api/admin/identity-directory/groups", headers=auth_headers
    ).json()["groups"]
    assert [group["value"] for group in groups] == ["access"]
    assert (
        client.get("/api/admin/identity-directory/users", headers=auth_headers).json()[
            "users"
        ][0]["name"]
        == "Access"
    )


@pytest.mark.parametrize(
    "provenance",
    [
        AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED,
        AuthenticationProvenance.LOCAL_SIMULATION,
        AuthenticationProvenance.LOCAL_SEMANTIC,
    ],
)
def test_production_gate_rejects_unverified_provenance(
    client: TestClient,
    auth_headers: dict[str, str],
    provenance: AuthenticationProvenance,
) -> None:
    def unverified_caller() -> CallerContext:
        return verified_caller().model_copy(update={"authentication": provenance})

    personal_app(client).dependency_overrides[get_caller_context] = unverified_caller
    assert (
        client.post("/api/me/identity-observations", headers=auth_headers).status_code
        == 401
    )
    assert (
        client.get("/api/admin/identity-directory/users", headers=auth_headers).json()[
            "users"
        ]
        == []
    )
