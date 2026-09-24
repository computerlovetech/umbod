import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import pytest
from fastapi.testclient import TestClient

from umbod.rest.main import create_app
from umbod.rest.settings import APISettings


@dataclass(frozen=True)
class AdminConnectorConfigurationRequest:
    token: str | None = None
    header_name: str | None = None


class AdminApiBoundary(Protocol):
    def get_admin_connector_configuration(
        self, request: AdminConnectorConfigurationRequest | None = None
    ) -> int: ...

    def get_system_health(self) -> int: ...


class JwtTokenFactory(Protocol):
    def valid_token_with_claim(self, claim_name: str, values: list[str]) -> str: ...

    def valid_token_without_claim(self, claim_name: str) -> str: ...

    def invalid_token(self) -> str: ...

    def untrusted_token(self) -> str: ...


class FastApiAdminApiBoundary:
    def __init__(self, client: TestClient, configured_header_name: str) -> None:
        self.client = client
        self.configured_header_name = configured_header_name

    def get_admin_connector_configuration(
        self, request: AdminConnectorConfigurationRequest | None = None
    ) -> int:
        headers = {}
        if request is not None and request.token is not None:
            headers[request.header_name or self.configured_header_name] = request.token
        response = self.client.get("/admin/connectors/catalog/slack/configuration", headers=headers)
        return response.status_code

    def get_system_health(self) -> int:
        response = self.client.get("/system/health")
        return response.status_code


class SemanticJwtTokenFactory:
    def valid_token_with_claim(self, claim_name: str, values: list[str]) -> str:
        return json.dumps({"signature": "trusted", "claims": {claim_name: values}})

    def valid_token_without_claim(self, claim_name: str) -> str:
        return json.dumps({"signature": "trusted", "claims": {"sub": "user@example.com"}})

    def invalid_token(self) -> str:
        return "not-a-valid-jwt"

    def untrusted_token(self) -> str:
        return json.dumps(
            {"signature": "untrusted", "claims": {"groups": ["umbod-admins"]}}
        )


ApiFixtureName = Literal["full_auth_api", "roles_auth_api", "simulation_api"]
RouteName = Literal["admin_connector_configuration", "system_health"]
TokenKind = Literal[
    "admin_group",
    "admin_role",
    "authorization_header_admin_group",
    "invalid",
    "untrusted",
    "without_groups_claim",
    "user_group",
    "readonly_group",
    "groups_admin",
]


@dataclass(frozen=True)
class AdminRouteScenario:
    api_fixture_name: ApiFixtureName
    route_name: RouteName
    expected_status_code: int | None = None
    unexpected_status_code: int | None = None
    token_kind: TokenKind | None = None


class AdminRouteAuthorizationAcceptance:
    def __init__(self, api: AdminApiBoundary, tokens: JwtTokenFactory) -> None:
        self.api = api
        self.tokens = tokens

    def assert_scenario(self, scenario: AdminRouteScenario) -> None:
        status_code = self._get_status_code(scenario)
        if scenario.expected_status_code is not None:
            assert status_code == scenario.expected_status_code
        if scenario.unexpected_status_code is not None:
            assert status_code != scenario.unexpected_status_code

    def _get_status_code(self, scenario: AdminRouteScenario) -> int:
        if scenario.route_name == "system_health":
            return self.api.get_system_health()
        return self.api.get_admin_connector_configuration(
            self._create_admin_request(scenario.token_kind)
        )

    def _create_admin_request(
        self, token_kind: TokenKind | None
    ) -> AdminConnectorConfigurationRequest | None:
        if token_kind is None:
            return None
        if token_kind == "admin_group":
            return AdminConnectorConfigurationRequest(
                self.tokens.valid_token_with_claim("groups", ["umbod-admins"])
            )
        if token_kind == "admin_role":
            return AdminConnectorConfigurationRequest(
                self.tokens.valid_token_with_claim("roles", ["admin"])
            )
        if token_kind == "authorization_header_admin_group":
            return AdminConnectorConfigurationRequest(
                self.tokens.valid_token_with_claim("groups", ["umbod-admins"]),
                "Authorization",
            )
        return AdminConnectorConfigurationRequest(self._create_token(token_kind))

    def _create_token(self, token_kind: TokenKind) -> str:
        token_by_kind = {
            "invalid": self.tokens.invalid_token,
            "untrusted": self.tokens.untrusted_token,
            "without_groups_claim": lambda: self.tokens.valid_token_without_claim("groups"),
            "user_group": lambda: self.tokens.valid_token_with_claim(
                "groups", ["umbod-users"]
            ),
            "readonly_group": lambda: self.tokens.valid_token_with_claim(
                "groups", ["umbod-admins-readonly"]
            ),
            "groups_admin": lambda: self.tokens.valid_token_with_claim("groups", ["admin"]),
        }
        return token_by_kind[token_kind]()


@pytest.fixture
def tokens() -> JwtTokenFactory:
    return SemanticJwtTokenFactory()


@pytest.fixture
def full_auth_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AdminApiBoundary:
    return _create_boundary(
        tmp_path,
        monkeypatch,
        APISettings(
            admin_authentication={
                "mode": "jwt",
                "jwt_header_name": "X-Forwarded-Access-Token",
                "jwks_url": "https://identity.example.com/.well-known/jwks.json",
                "membership_claim": "groups",
                "required_membership": "umbod-admins",
            }
        ),
    )


@pytest.fixture
def roles_auth_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AdminApiBoundary:
    return _create_boundary(
        tmp_path,
        monkeypatch,
        APISettings(
            admin_authentication={
                "mode": "jwt",
                "jwt_header_name": "X-Forwarded-Access-Token",
                "jwks_url": "https://identity.example.com/.well-known/jwks.json",
                "membership_claim": "roles",
                "required_membership": "admin",
            }
        ),
    )


@pytest.fixture
def simulation_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AdminApiBoundary:
    return _create_boundary(
        tmp_path,
        monkeypatch,
        APISettings(admin_authentication={"mode": "simulation", "simulated_admin": True}),
    )


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(
            AdminRouteScenario(
                "full_auth_api", "admin_connector_configuration", 200, token_kind="admin_group"
            ),
            id="admin_group_member_accesses_admin_route_in_full_authentication_mode",
        ),
        pytest.param(
            AdminRouteScenario(
                "roles_auth_api", "admin_connector_configuration", 200, token_kind="admin_role"
            ),
            id="admin_role_member_accesses_admin_route_using_configured_roles_claim",
        ),
        pytest.param(
            AdminRouteScenario("simulation_api", "admin_connector_configuration", 200),
            id="developer_accesses_admin_route_in_simulation_mode",
        ),
        pytest.param(
            AdminRouteScenario(
                "full_auth_api",
                "admin_connector_configuration",
                401,
                token_kind="authorization_header_admin_group",
            ),
            id="admin_route_authorization_uses_configured_jwt_header_only",
        ),
        pytest.param(
            AdminRouteScenario("full_auth_api", "system_health", 200),
            id="system_route_remains_unauthenticated",
        ),
        pytest.param(
            AdminRouteScenario("full_auth_api", "admin_connector_configuration", 401),
            id="missing_jwt_on_admin_route_is_unauthorized",
        ),
        pytest.param(
            AdminRouteScenario(
                "full_auth_api", "admin_connector_configuration", 401, token_kind="invalid"
            ),
            id="invalid_jwt_on_admin_route_is_unauthorized",
        ),
        pytest.param(
            AdminRouteScenario(
                "full_auth_api", "admin_connector_configuration", 401, token_kind="untrusted"
            ),
            id="jwt_signed_by_untrusted_key_is_unauthorized",
        ),
        pytest.param(
            AdminRouteScenario(
                "full_auth_api",
                "admin_connector_configuration",
                403,
                token_kind="without_groups_claim",
            ),
            id="jwt_without_configured_membership_claim_is_forbidden",
        ),
        pytest.param(
            AdminRouteScenario(
                "full_auth_api", "admin_connector_configuration", 403, token_kind="user_group"
            ),
            id="authenticated_user_without_required_group_is_forbidden",
        ),
        pytest.param(
            AdminRouteScenario(
                "full_auth_api", "admin_connector_configuration", 403, token_kind="readonly_group"
            ),
            id="configured_required_membership_value_grants_access_only_on_exact_membership",
        ),
        pytest.param(
            AdminRouteScenario("full_auth_api", "admin_connector_configuration", 401),
            id="full_authentication_mode_does_not_simulate_admin_user",
        ),
        pytest.param(
            AdminRouteScenario(
                "roles_auth_api", "admin_connector_configuration", 403, token_kind="groups_admin"
            ),
            id="membership_claim_value_is_read_from_the_configured_field",
        ),
        pytest.param(
            AdminRouteScenario("full_auth_api", "admin_connector_configuration", 401),
            id="authentication_mode_is_explicit_and_mutually_exclusive",
        ),
        pytest.param(
            AdminRouteScenario("simulation_api", "admin_connector_configuration", 200),
            id="simulation_mode_is_explicit_and_separate_from_full_authentication_mode",
        ),
    ],
)
def test_admin_route_authorization_acceptance(
    scenario: AdminRouteScenario,
    request: pytest.FixtureRequest,
    tokens: JwtTokenFactory,
) -> None:
    api = request.getfixturevalue(scenario.api_fixture_name)
    AdminRouteAuthorizationAcceptance(api, tokens).assert_scenario(scenario)


def _create_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: APISettings
) -> AdminApiBoundary:
    availability_path = tmp_path / "connector-availability.json"
    availability_path.write_text(json.dumps({"connectors": [{"id": "slack"}]}), encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(availability_path))
    return FastApiAdminApiBoundary(
        TestClient(create_app(settings=settings)), "X-Forwarded-Access-Token"
    )
