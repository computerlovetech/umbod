import json
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support.personal_oauth_metadata import InMemoryPersonalOAuthMetadataProvider
from tests.support.personal_oauth_setup import install_api_setup_validation
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.metadata import DiscoveredPersonalOAuthMetadataProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal_oauth_metadata import DiscoveredPersonalOAuthMetadata
from umbod.rest.connectors.downstream_mcp.personal_oauth_metadata import get_metadata_provider
from tests.umbod.rest.connectors.downstream_mcp.personal_connections.test_personal_oauth_routes import OAuthApi, oauth_api as oauth_api
from .test_personal_catalogue import client as client, payload


URL = "/api/admin/connectors/mcp/personal-oauth/discovery"
BODY = {"endpoint_url": "https://resource.example/mcp", "issuer_selection": {"kind": "automatic"}}


def admin_app(client: TestClient) -> FastAPI:
    app = cast(FastAPI, client.app)
    return cast(FastAPI, next(route.app for route in app.routes if getattr(route, "path", "") == "/api/admin"))


@pytest.fixture
def metadata_provider(client: TestClient) -> InMemoryPersonalOAuthMetadataProvider:
    provider = InMemoryPersonalOAuthMetadataProvider(DiscoveredPersonalOAuthMetadata(
        endpoint_url="https://resource.example/mcp", issuer_url="https://issuer.example",
        available_scopes=("read",), scope_source="resource", automatic_registration="unavailable",
        automatic_client={"kind": "unavailable"}, token_endpoint_auth_methods=("none",),
    ))

    def provide() -> InMemoryPersonalOAuthMetadataProvider:
        return provider

    admin_app(client).dependency_overrides[get_metadata_provider] = provide
    return provider


def test_preview_is_read_only_without_oauth_execution(client: TestClient, metadata_provider: InMemoryPersonalOAuthMetadataProvider) -> None:
    result = client.post(URL, json=BODY)
    assert result.status_code == 200
    assert result.json()["kind"] == "discovered"
    assert result.headers["Cache-Control"] == "no-store"
    assert len(metadata_provider.commands) == 1
    assert client.get("/api/admin/connectors/mcp").json() == {"connectors": []}


@pytest.mark.parametrize("body", [{}, [], {"endpoint_url": "http://private-secret.example", "issuer_selection": {"kind": "automatic"}}, BODY | {"extra": "private-secret"}, BODY | {"issuer_selection": {"kind": "selected"}}, BODY | {"endpoint_url": "https://resource.example/" + "x" * 4096}])
def test_preview_rejects_invalid_input_without_reflection(client: TestClient, metadata_provider: InMemoryPersonalOAuthMetadataProvider, body: object) -> None:
    result = client.post(URL, json=body)
    assert result.status_code == 422
    assert result.json() == {"detail": {"code": "personal_oauth_discovery_failed", "stage": "discovery", "reason": "invalid_response"}}
    assert result.headers["Cache-Control"] == "no-store"
    assert metadata_provider.commands == []


def test_preview_accepts_body_at_exact_limit(client: TestClient, metadata_provider: InMemoryPersonalOAuthMetadataProvider) -> None:
    body = json.dumps(BODY).encode()
    result = client.post(URL, content=body + b" " * (12288 - len(body)), headers={"Content-Type": "application/json"})
    assert result.status_code == 200
    assert len(metadata_provider.commands) == 1


def test_preview_body_is_bounded_before_provider(client: TestClient, metadata_provider: InMemoryPersonalOAuthMetadataProvider) -> None:
    result = client.post(URL, content=b" " * 12289, headers={"Content-Type": "application/json"})
    assert result.status_code == 413
    assert result.headers["Cache-Control"] == "no-store"
    assert metadata_provider.commands == []


@pytest.mark.parametrize("client", [False], indirect=True)
def test_preview_requires_personal_connections_registration(client: TestClient) -> None:
    result = client.post(URL, json=BODY)
    assert result.status_code == 404
    assert result.headers["Cache-Control"] == "no-store"


def test_preview_is_admin_only_and_not_mounted_on_personal_api(oauth_api: OAuthApi) -> None:
    result = oauth_api.client.post(URL, json=BODY)
    assert result.status_code == 401
    assert result.headers["Cache-Control"] == "no-store"
    non_admin = {"X-Access": json.dumps({"signature": "trusted", "claims": {"sub": "alice", "groups": ["team"]}})}
    result = oauth_api.client.post(URL, headers=non_admin, json=BODY)
    assert result.status_code == 403
    assert result.headers["Cache-Control"] == "no-store"
    assert oauth_api.client.post(URL.replace("/admin/", "/me/"), headers={"X-Access": "alice"}, json=BODY).status_code == 404
    cookie_result = oauth_api.client.post(URL, headers={**oauth_api.admin_headers, "Cookie": "session=fixture"}, json=BODY)
    assert cookie_result.status_code == 403
    assert cookie_result.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("status,body,expected,reason", [(503, b"private-secret", 502, "provider_rejected"), (200, b"private-secret", 422, "invalid_response")])
def test_preview_returns_only_sanitized_failure_evidence(client: TestClient, status: int, body: bytes, expected: int, reason: str) -> None:
    transport = InMemoryOAuthHttpTransport([OAuthHttpResponse(status=status, body=body)])
    provider = DiscoveredPersonalOAuthMetadataProvider(transport)

    def provide() -> DiscoveredPersonalOAuthMetadataProvider:
        return provider

    admin_app(client).dependency_overrides[get_metadata_provider] = provide
    result = client.post(URL, json=BODY)
    assert result.status_code == expected
    assert result.json() == {"detail": {"code": "personal_oauth_discovery_failed", "stage": "discovery", "reason": reason}}
    assert result.headers["Cache-Control"] == "no-store"
    assert "private-secret" not in result.text


def test_approved_issuer_roundtrip_noop_and_replacement_invalidates_setup(client: TestClient) -> None:
    body = payload()
    body["configuration"]["oauth_configuration"] = {"requested_scopes": [], "client": {"kind": "dynamic_public", "approved_issuers": ["https://issuer.example"]}}
    created = client.post("/api/admin/connectors/mcp/personal-oauth", json=body)
    assert created.status_code == 201
    connector_id = created.json()["connector_id"]
    url = f"/api/admin/connectors/mcp/{connector_id}/personal-oauth"
    initial = client.get(url).json()
    assert initial["client"] == {"kind": "dynamic_public", "approved_issuers": ["https://issuer.example"]}
    settings = {"requested_scopes": initial["requested_scopes"], "client": initial["client"]}
    unchanged = client.put(url, json={"expected_revision": initial["revision"], "settings": settings})
    assert unchanged.json() == initial
    install_api_setup_validation(client, {}, connector_id)
    setup_url = f"/api/admin/connectors/mcp/{connector_id}/personal-oauth/setup"
    assert client.get(setup_url).json()["state"]["status"] == "validated"
    settings["client"] = {"kind": "dynamic_public", "approved_issuers": ["https://replacement.example"]}
    replaced = client.put(url, json={"expected_revision": initial["revision"], "settings": settings})
    assert replaced.status_code == 200
    assert replaced.json()["revision"] != initial["revision"]
    assert client.get(url).json()["client"] == settings["client"]
    assert client.get(setup_url).json()["state"]["status"] == "required"


def test_legacy_dynamic_client_response_keeps_unbound_shape(client: TestClient) -> None:
    created = client.post("/api/admin/connectors/mcp/personal-oauth", json=payload()).json()
    result = client.get(f'/api/admin/connectors/mcp/{created["connector_id"]}/personal-oauth')
    assert result.json()["client"] == {"kind": "dynamic_public"}
