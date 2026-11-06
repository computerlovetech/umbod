"""Acceptance tests for issue #37: explain personal OAuth scope configuration failures.

The provider is the real discovered OAuth adapter running against local fixtures through the
injectable in-memory HTTP transport. Every fixture satisfies the unrelated OAuth requirements
(issuer, redirect URI, authentication method, grant types, state and PKCE) so each failure isolates
the scope mismatch.
"""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from umbod.config import AppConfig
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import (
    InMemoryOAuthHttpTransport,
    OAuthHttpResponse,
)
from umbod.logging import OpenTelemetryJsonFormatter
from umbod.rest.connectors.downstream_mcp.dependencies import get_downstream_connector_probe
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_dependencies import get_personal_oauth_provider
from umbod.rest.main import create_app

from .test_personal_connection_routes import ForbiddenProbe, UserVerifier


ENDPOINT = "https://tools.example/mcp"
ISSUER = "https://issuer.example"
CALLBACK = "http://localhost:18010/api/oauth/downstream-mcp/callback"
SENTINELS = (
    "sentinel-registration-access-token", "sentinel-raw-response-body",
    "sentinel-software-statement", "sentinel-client-uri",
)


def _json(value: dict[str, object]) -> OAuthHttpResponse:
    return OAuthHttpResponse(status=200, body=json.dumps(value).encode())


def provider_fixture(registered_scope: str | None) -> list[OAuthHttpResponse]:
    """One successful discovery and dynamic registration, optionally returning a scope."""
    client: dict[str, object] = {
        "client_id": "registered-client", "redirect_uris": [CALLBACK],
        "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "application_type": "native",
        "registration_access_token": SENTINELS[0], "client_name": SENTINELS[1],
        "software_statement": SENTINELS[2], "client_uri": "https://" + SENTINELS[3] + ".example",
    }
    if registered_scope is not None:
        client["scope"] = registered_scope
    return [
        _json({"resource": ENDPOINT, "authorization_servers": [ISSUER]}),
        _json({
            "issuer": ISSUER, "authorization_endpoint": ISSUER + "/authorize",
            "token_endpoint": ISSUER + "/token", "registration_endpoint": ISSUER + "/register",
            "code_challenge_methods_supported": ["S256"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "response_types_supported": ["code"], "token_endpoint_auth_methods_supported": ["none"],
            "authorization_response_iss_parameter_supported": True,
        }),
        _json(client),
    ]


@dataclass
class ScopeApi:
    client: TestClient
    app: FastAPI
    admin_headers: dict[str, str]
    transport: InMemoryOAuthHttpTransport

    def create_connector(self, display_name: str, scopes: tuple[str, ...] = ()) -> str:
        slug = display_name.lower().replace(" ", "-")
        response = self.client.post("/api/admin/connectors/mcp/personal-oauth", headers=self.admin_headers, json={
            "metadata": {
                "display_name": display_name, "capability_description": "Personal account capabilities",
                "public_path": "/mcp/proxies/" + slug,
            },
            "configuration": {"endpoint_url": ENDPOINT},
        })
        response.raise_for_status()
        connector_id = response.json()["connector_id"]
        if scopes:
            self.configure_scopes(connector_id, scopes)
        self.client.put(f"/api/admin/connectors/mcp/{connector_id}/publication", headers=self.admin_headers).raise_for_status()
        self.client.put("/api/admin/mcp-permissions/groups/team/permissions", headers=self.admin_headers, json={
            "connectors": [{"connector_id": connector_id, "permission_status": "enabled"}],
        }).raise_for_status()
        self.client.put(
            f"/api/me/connectors/mcp/{connector_id}/enablement", headers={"X-Access": "alice"}, json={"enabled": True},
        ).raise_for_status()
        return connector_id

    def configure_scopes(self, connector_id: str, scopes: tuple[str, ...]) -> None:
        url = f"/api/admin/connectors/mcp/{connector_id}/personal-oauth"
        current = self.client.get(url, headers=self.admin_headers)
        current.raise_for_status()
        self.client.put(url, headers=self.admin_headers, json={
            "expected_revision": current.json()["revision"],
            "settings": {"requested_scopes": list(scopes), "client": {"kind": "dynamic_public"}},
        }).raise_for_status()

    def provider_will_register(self, registered_scope: str | None) -> None:
        self.transport.responses.extend(provider_fixture(registered_scope))

    def start(self, connector_id: str) -> Response:
        return self.client.post(
            f"/api/me/connectors/mcp/{connector_id}/oauth/attempts", headers={"X-Access": "alice"}, json={},
        )


@pytest.fixture
def scope_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ScopeApi]:
    deployment = tmp_path / "deployment.json"
    deployment.write_text('{"connectors": []}', encoding="utf-8")
    monkeypatch.setenv("UMBOD_CONNECTOR_DEPLOYMENT_CONFIGURATION_PATH", str(deployment))
    settings = AppConfig(
        connector_store={"type": "sqlite", "sqlite_path": str(tmp_path / "scopes.sqlite3")},
        connector_security={"configuration_secret": "test-personal-oauth-encryption-key"},
        rest={"metrics_enabled": False},
        endpoints={"site_base_url": "http://localhost:3010/", "api_base_url": "http://localhost:18010"},
        admin_authentication={
            "mode": "jwt", "environment": "development", "required_membership": "admins",
            "membership_claim": "groups", "jwt_header_name": "X-Access",
        },
        mcp={"permission_group_claim": "groups"},
        personal_connections={"enabled": True, "oauth_enabled": True, "identity_namespace": "test:oauth-scopes"},
    )
    app = create_app(settings, [], user_verifier=UserVerifier())
    transport = InMemoryOAuthHttpTransport([])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.LOCAL_DEVELOPMENT, transport)
    for route in app.routes:
        child = getattr(route, "app", None)
        if isinstance(child, FastAPI):
            child.dependency_overrides[get_personal_oauth_provider] = lambda: provider
    admin_app = next(route.app for route in app.routes if getattr(route, "path", "") == "/api/admin")
    admin_app.dependency_overrides[get_downstream_connector_probe] = ForbiddenProbe
    admin_headers = {"X-Access": json.dumps({"signature": "trusted", "claims": {"sub": "admin", "groups": ["admins"]}})}
    with TestClient(app) as client:
        yield ScopeApi(client, app, admin_headers, transport)


EXAMPLES = pytest.mark.parametrize("connector,scope", [
    ("Document service", "documents.read"),
    ("Task service", "tasks:read"),
])


# Rule: Scope configuration failures explain the cause and remedy

@EXAMPLES
def test_api_explains_unconfigured_provider_default_scope(scope_api: ScopeApi, connector: str, scope: str) -> None:
    connector_id = scope_api.create_connector(connector)
    scope_api.provider_will_register(scope)

    response = scope_api.start(connector_id)

    assert response.status_code == 422
    assert response.json() == {"detail": {
        "code": "personal_oauth_scope_mismatch", "step": "registration",
        "configured_scopes": [], "returned_scopes": [scope],
    }}
    registration = json.loads(scope_api.transport.requests[-1].body.get_secret_value())
    assert "scope" not in registration


def test_scope_mismatch_creates_no_pending_authorization_attempt(scope_api: ScopeApi) -> None:
    connector_id = scope_api.create_connector("Document service")
    scope_api.provider_will_register("documents.read")
    assert scope_api.start(connector_id).status_code == 422

    # A pending attempt would make a fresh start conflict (409); the failed attempt must not block it.
    scope_api.provider_will_register(None)
    retried = scope_api.start(connector_id)

    assert retried.status_code == 201
    assert retried.json()["status"] == "pending"


def test_scope_mismatch_warning_identifies_cause_without_credentials(
    scope_api: ScopeApi, caplog: pytest.LogCaptureFixture,
) -> None:
    connector_id = scope_api.create_connector("Document service")
    scope_api.provider_will_register("documents.read")

    with caplog.at_level(logging.WARNING, logger="umbod.personal_oauth"):
        response = scope_api.start(connector_id)

    records = [record for record in caplog.records if record.name == "umbod.personal_oauth"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    emitted = json.loads(OpenTelemetryJsonFormatter("umbod-test").format(records[0]))
    assert emitted["severity_text"] == "WARNING"
    attributes = emitted["attributes"]
    assert attributes["connector.id"] == connector_id
    assert attributes["oauth.step"] == "registration"
    assert attributes["reason"] == "scope_mismatch"
    assert attributes["oauth.scopes.returned"] == "documents.read"
    assert attributes["oauth.scopes.configured_count"] == 0
    serialized = json.dumps(emitted) + response.text + caplog.text
    for sentinel in SENTINELS + ("registered-client", "code_challenge", "state="):
        assert sentinel not in serialized


def test_unrelated_registration_rejection_remains_generic(scope_api: ScopeApi, caplog: pytest.LogCaptureFixture) -> None:
    connector_id = scope_api.create_connector("Document service")
    fixture = provider_fixture("documents.read")
    client = json.loads(fixture[2].body)
    client["redirect_uris"] = ["https://other.example/callback"]
    scope_api.transport.responses.extend([*fixture[:2], _json(client)])

    with caplog.at_level(logging.WARNING, logger="umbod.personal_oauth"):
        response = scope_api.start(connector_id)

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "personal_oauth_provider_unsupported"}}
    assert not [record for record in caplog.records if record.name == "umbod.personal_oauth"]


# Rule: Explicit scope configuration permits sign-in without expanding permissions

@EXAMPLES
def test_matching_configured_scope_permits_sign_in_to_start(scope_api: ScopeApi, connector: str, scope: str) -> None:
    connector_id = scope_api.create_connector(connector, scopes=(scope,))
    scope_api.provider_will_register(scope)

    response = scope_api.start(connector_id)

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    assert query["scope"] == [scope]
    assert query["code_challenge_method"] == ["S256"]
    registration = json.loads(scope_api.transport.requests[-1].body.get_secret_value())
    assert registration["scope"] == scope


def test_configured_scopes_returned_in_a_different_order_permit_sign_in(scope_api: ScopeApi) -> None:
    connector_id = scope_api.create_connector("Document service", scopes=("documents.read", "tasks:read"))
    scope_api.provider_will_register("tasks:read documents.read")

    response = scope_api.start(connector_id)

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert parse_qs(urlsplit(response.json()["authorization_url"]).query)["scope"] == ["documents.read tasks:read"]


def test_returned_scope_beyond_configured_request_is_a_mismatch(scope_api: ScopeApi) -> None:
    connector_id = scope_api.create_connector("Document service", scopes=("documents.read",))
    scope_api.provider_will_register("documents.read documents.write")

    response = scope_api.start(connector_id)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "personal_oauth_scope_mismatch"
    assert response.json()["detail"]["returned_scopes"] == ["documents.read", "documents.write"]
