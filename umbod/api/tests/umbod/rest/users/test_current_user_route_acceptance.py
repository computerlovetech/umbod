import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


@dataclass(frozen=True)
class CurrentUserRequest:
    token: str | None = None


@dataclass(frozen=True)
class CurrentUserResponse:
    status_code: int
    body: dict[str, Any]


class CurrentUserApiBoundary(Protocol):
    def get_current_user(
        self, request: CurrentUserRequest | None = None
    ) -> CurrentUserResponse: ...


class JwtTokenFactory(Protocol):
    def trusted_token(self, claims: dict[str, object]) -> str: ...

    def invalid_token(self) -> str: ...


class FastApiCurrentUserApiBoundary:
    def __init__(self, client: TestClient, configured_header_name: str) -> None:
        self.client = client
        self.configured_header_name = configured_header_name

    def get_current_user(self, request: CurrentUserRequest | None = None) -> CurrentUserResponse:
        headers = {}
        if request is not None and request.token is not None:
            headers[self.configured_header_name] = request.token
        response = self.client.get("/admin/users", headers=headers)
        return CurrentUserResponse(status_code=response.status_code, body=response.json())


class SemanticJwtTokenFactory:
    def trusted_token(self, claims: dict[str, object]) -> str:
        return json.dumps({"signature": "trusted", "claims": claims})

    def invalid_token(self) -> str:
        return "not-a-valid-jwt"


@pytest.fixture
def tokens() -> JwtTokenFactory:
    return SemanticJwtTokenFactory()


def create_current_user_api(
    settings: APISettings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> CurrentUserApiBoundary:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "slack"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    return FastApiCurrentUserApiBoundary(
        TestClient(create_app(settings=settings)), "X-Forwarded-Access-Token"
    )


@pytest.fixture
def current_user_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CurrentUserApiBoundary:
    settings = APISettings(
        admin_authentication={
            "mode": "jwt",
            "jwt_header_name": "X-Forwarded-Access-Token",
            "jwks_url": "https://identity.example.com/.well-known/jwks.json",
            "membership_claim": "groups",
            "required_membership": "umbod-admins",
        }
    )
    return create_current_user_api(settings, tmp_path, monkeypatch)


def test_simulation_mode_returns_simulated_user_without_forwarded_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user_api = create_current_user_api(
        APISettings(
            admin_authentication={
                "mode": "simulation",
                "simulated_user_id": "sim-user-123",
                "simulated_user_email": "sim-user@example.com",
                "simulated_user_name": "Simulated User",
            }
        ),
        tmp_path,
        monkeypatch,
    )

    response = current_user_api.get_current_user()

    assert response.status_code == 200
    assert response.body == {
        "id": "sim-user-123",
        "email": "sim-user@example.com",
        "name": "Simulated User",
        "picture": None,
    }


def test_authenticated_caller_retrieves_own_user_details(
    current_user_api: CurrentUserApiBoundary,
    tokens: JwtTokenFactory,
) -> None:
    response = current_user_api.get_current_user(
        CurrentUserRequest(
            tokens.trusted_token(
                {
                    "sub": "user-123",
                    "email": "alex@example.com",
                    "name": "Alex Morgan",
                    "groups": ["umbod-admins"],
                }
            )
        )
    )

    assert response.status_code == 200
    assert response.body == {
        "id": "user-123",
        "email": "alex@example.com",
        "name": "Alex Morgan",
        "picture": None,
    }


def test_authenticated_caller_can_use_authorization_bearer_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tokens: JwtTokenFactory,
) -> None:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "slack"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    current_user_api = FastApiCurrentUserApiBoundary(
        TestClient(
            create_app(
                settings=APISettings(
                    admin_authentication={
                        "mode": "jwt",
                        "jwt_header_name": "Authorization",
                        "jwks_url": "https://identity.example.com/.well-known/jwks.json",
                    }
                )
            )
        ),
        "Authorization",
    )

    response = current_user_api.get_current_user(
        CurrentUserRequest(
            f"Bearer {tokens.trusted_token({'sub': 'user-123', 'email': 'alex@example.com', 'groups': ['umbod-admins']})}"
        )
    )

    assert response.status_code == 200
    assert response.body == {
        "id": "user-123",
        "email": "alex@example.com",
        "name": "unknown",
        "picture": None,
    }


def test_authenticated_caller_without_name_claim_gets_unknown_name(
    current_user_api: CurrentUserApiBoundary,
    tokens: JwtTokenFactory,
) -> None:
    response = current_user_api.get_current_user(
        CurrentUserRequest(
            tokens.trusted_token(
                {"sub": "user-123", "email": "alex@example.com", "groups": ["umbod-admins"]}
            )
        )
    )

    assert response.status_code == 200
    assert response.body == {
        "id": "user-123",
        "email": "alex@example.com",
        "name": "unknown",
        "picture": None,
    }


@pytest.mark.parametrize(
    "current_user_request",
    [
        pytest.param(None, id="missing_authentication"),
        pytest.param(CurrentUserRequest("not-a-valid-jwt"), id="invalid_authentication"),
    ],
)
def test_current_user_requires_valid_authentication(
    current_user_api: CurrentUserApiBoundary,
    current_user_request: CurrentUserRequest | None,
) -> None:
    response = current_user_api.get_current_user(current_user_request)

    assert response.status_code == 401
    assert response.body == {"detail": "Unauthorized"}


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param(
            {"email": "alex@example.com", "groups": ["umbod-admins"]},
            id="missing_subject_claim",
        ),
        pytest.param(
            {"sub": "user-123", "groups": ["umbod-admins"]}, id="missing_email_claim"
        ),
    ],
)
def test_current_user_requires_subject_and_email_claims(
    current_user_api: CurrentUserApiBoundary,
    tokens: JwtTokenFactory,
    claims: dict[str, object],
) -> None:
    response = current_user_api.get_current_user(CurrentUserRequest(tokens.trusted_token(claims)))

    assert response.status_code == 401
    assert response.body == {"detail": "Unauthorized"}


def test_authenticated_caller_retrieves_standard_picture_claim(
    current_user_api: CurrentUserApiBoundary,
    tokens: JwtTokenFactory,
) -> None:
    response = current_user_api.get_current_user(
        CurrentUserRequest(
            tokens.trusted_token(
                {
                    "sub": "user-123",
                    "email": "alex@example.com",
                    "name": "Alex Morgan",
                    "picture": "https://example.com/alex.png",
                    "groups": ["umbod-admins"],
                }
            )
        )
    )

    assert response.status_code == 200
    assert response.body == {
        "id": "user-123",
        "email": "alex@example.com",
        "name": "Alex Morgan",
        "picture": "https://example.com/alex.png",
    }


@pytest.mark.parametrize(
    "picture_claim",
    [
        pytest.param(123, id="number"),
        pytest.param({"url": "https://example.com/alex.png"}, id="object"),
        pytest.param(["https://example.com/alex.png"], id="array"),
    ],
)
def test_authenticated_caller_with_non_string_picture_claim_gets_no_picture(
    current_user_api: CurrentUserApiBoundary,
    tokens: JwtTokenFactory,
    picture_claim: object,
) -> None:
    response = current_user_api.get_current_user(
        CurrentUserRequest(
            tokens.trusted_token(
                {
                    "sub": "user-123",
                    "email": "alex@example.com",
                    "name": "Alex Morgan",
                    "picture": picture_claim,
                    "groups": ["umbod-admins"],
                }
            )
        )
    )

    assert response.status_code == 200
    assert response.body == {
        "id": "user-123",
        "email": "alex@example.com",
        "name": "Alex Morgan",
        "picture": None,
    }


def test_non_admin_authenticated_caller_cannot_retrieve_current_user_details(
    current_user_api: CurrentUserApiBoundary,
    tokens: JwtTokenFactory,
) -> None:
    response = current_user_api.get_current_user(
        CurrentUserRequest(
            tokens.trusted_token(
                {
                    "sub": "jwt-user-123",
                    "email": "jwt-alex@example.com",
                    "name": "JWT Alex",
                    "groups": ["umbod-users"],
                    "roles": ["member"],
                    "avatar_url": "https://example.com/avatar.png",
                    "created_at": "2026-06-16T12:00:00Z",
                    "last_login_at": "2026-06-16T12:30:00Z",
                }
            )
        )
    )

    assert response.status_code == 403
    assert response.body == {"detail": "Forbidden"}
