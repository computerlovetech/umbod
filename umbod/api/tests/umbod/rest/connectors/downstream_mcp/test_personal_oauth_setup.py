import json
import logging
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support.application_failures import CapturingApplicationFailures
from tests.support.personal_oauth_setup import SuccessfulSetupProvider
from tests.umbod.rest.connectors.downstream_mcp.personal_connections.test_personal_oauth_routes import OAuthApi, oauth_api as oauth_api
from tests.umbod.rest.connectors.downstream_mcp.personal_connections.test_oauth_diagnostics import discovery_responses, response
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.setup import DiscoveredPersonalOAuthSetupProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport
from umbod.core.connectors.downstream_mcp.personal_oauth_setup.models import DiscoverPersonalOAuthSetup, PersonalOAuthSetupDiscovery, PersonalOAuthSetupValidation, ValidatePersonalOAuthSetup
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_diagnostics import get_oauth_application_failures
from umbod.rest.connectors.downstream_mcp.personal_oauth_setup import get_setup_provider
from .test_personal_catalogue import client as client, payload


class RecordingSetupProvider(SuccessfulSetupProvider):
    def __init__(self) -> None:
        self.discoveries: list[DiscoverPersonalOAuthSetup] = []
        self.validations: list[ValidatePersonalOAuthSetup] = []

    async def discover(self, command: DiscoverPersonalOAuthSetup) -> PersonalOAuthSetupDiscovery:
        self.discoveries.append(command)
        return await super().discover(command)

    async def validate(self, command: ValidatePersonalOAuthSetup) -> PersonalOAuthSetupValidation:
        self.validations.append(command)
        return await super().validate(command)


@dataclass(frozen=True)
class SetupApi:
    client: TestClient
    provider: RecordingSetupProvider
    connector_id: str

    @property
    def url(self) -> str:
        return f"/api/admin/connectors/mcp/{self.connector_id}/personal-oauth/setup"


@pytest.fixture
def setup_api(client: TestClient) -> SetupApi:
    app = client.app
    if not isinstance(app, FastAPI):
        raise TypeError("Expected API application")
    admin = next(route.app for route in app.routes if getattr(route, "path", "") == "/api/admin")
    provider = RecordingSetupProvider()

    def provide() -> RecordingSetupProvider:
        return provider

    admin.dependency_overrides[get_setup_provider] = provide
    created = client.post("/api/admin/connectors/mcp/personal-oauth", json=payload())
    created.raise_for_status()
    return SetupApi(client, provider, created.json()["connector_id"])


def test_setup_get_has_no_provider_io_and_uses_configured_callback(setup_api: SetupApi) -> None:
    result = setup_api.client.get(setup_api.url, headers={"Host": "untrusted.example"})
    assert result.status_code == 200
    assert result.json()["state"] == {"status": "required"}
    assert "untrusted" not in result.json()["redirect_uri"]
    assert result.headers["Cache-Control"] == "no-store"
    assert setup_api.provider.discoveries == setup_api.provider.validations == []


def test_setup_validation_is_required_before_publication(setup_api: SetupApi) -> None:
    publication = f"/api/admin/connectors/mcp/{setup_api.connector_id}/publication"
    rejected = setup_api.client.put(publication)
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "personal_oauth_setup_required"
    revision = setup_api.client.get(setup_api.url).json()["revision"]
    validated = setup_api.client.post(setup_api.url + "/validation", json={"expected_revision": revision})
    assert validated.status_code == 200
    assert validated.json()["state"]["status"] == "validated"
    assert validated.json()["state"]["checked_at"]
    assert setup_api.client.put(publication).status_code == 200
    assert len(setup_api.provider.validations) == 1
    assert "authorization_url" not in validated.text


def test_setup_discovery_does_not_approve_scopes_or_authorize_publication(setup_api: SetupApi) -> None:
    revision = setup_api.client.get(setup_api.url).json()["revision"]
    discovered = setup_api.client.post(setup_api.url + "/discovery", json={"expected_revision": revision})
    assert discovered.status_code == 200
    assert discovered.json()["state"]["status"] == "discovered"
    assert len(setup_api.provider.discoveries) == 1
    assert setup_api.provider.validations == []
    assert setup_api.client.put(f"/api/admin/connectors/mcp/{setup_api.connector_id}/publication").status_code == 409


@pytest.mark.parametrize("body", [{}, {"expected_revision": "x", "status": "validated"}, {"expected_revision": "x", "endpoint_url": "https://sentinel.example"}, {"expected_revision": "x", "client_secret": "sentinel-secret"}, {"expected_revision": 123}, None, []])
def test_setup_rejects_forged_or_unbounded_inputs_without_reflection(setup_api: SetupApi, body: object) -> None:
    result = setup_api.client.post(setup_api.url + "/validation", json=body)
    assert result.status_code == 422
    assert result.json() == {"detail": {"code": "invalid_personal_oauth_setup"}}
    assert "sentinel" not in result.text
    assert setup_api.provider.validations == []


def test_setup_body_is_stream_bounded_before_provider_io(setup_api: SetupApi) -> None:
    result = setup_api.client.post(setup_api.url + "/validation", content=b" " * 2049, headers={"Content-Type": "application/json"})
    assert result.status_code == 413
    assert setup_api.provider.validations == []


def test_setup_rejects_stale_revision_without_provider_io(setup_api: SetupApi) -> None:
    result = setup_api.client.post(setup_api.url + "/validation", json={"expected_revision": "stale"})
    assert result.status_code == 409
    assert result.json() == {"detail": {"code": "personal_oauth_setup_conflict"}}
    assert setup_api.provider.validations == []


def test_setup_is_admin_only_and_not_mounted_on_personal_api(oauth_api: OAuthApi) -> None:
    url = f"/api/admin/connectors/mcp/{oauth_api.connector_id}/personal-oauth/setup"
    assert oauth_api.client.get(url).status_code == 401
    non_admin = {"X-Access": json.dumps({"signature": "trusted", "claims": {"sub": "alice", "groups": ["team"]}})}
    assert oauth_api.client.get(url, headers=non_admin).status_code == 403
    assert oauth_api.client.post(url + "/validation", headers=non_admin, json={"expected_revision": "legacy"}).status_code == 403
    personal = url.replace("/api/admin/", "/api/me/")
    assert oauth_api.client.get(personal, headers={"X-Access": "alice"}).status_code == 404


def test_real_provider_validation_checks_metadata_without_registration_or_warning(oauth_api: OAuthApi, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    admin = next(route.app for route in oauth_api.app.routes if getattr(route, "path", "") == "/api/admin")
    transport = InMemoryOAuthHttpTransport(discovery_responses() + [response({"client_id": "sentinel-client", "scope": "candidate.read", "redirect_uris": ["http://localhost:18010/api/oauth/downstream-mcp/callback"], "token_endpoint_auth_method": "none", "grant_types": ["authorization_code"], "response_types": ["code"]}, status=201)])
    provider = DiscoveredPersonalOAuthSetupProvider(CallbackURLPolicy.LOCAL_DEVELOPMENT, transport)

    def provide() -> DiscoveredPersonalOAuthSetupProvider:
        return provider

    admin.dependency_overrides[get_setup_provider] = provide
    captured = CapturingApplicationFailures()
    admin.dependency_overrides[get_oauth_application_failures]().connect("test.setup.capture", captured.send)
    url = f"/api/admin/connectors/mcp/{oauth_api.connector_id}/personal-oauth/setup"
    revision = oauth_api.client.get(url, headers=oauth_api.admin_headers).json()["revision"]
    result = oauth_api.client.post(url + "/validation", headers=oauth_api.admin_headers, json={"expected_revision": revision})
    assert result.status_code == 200
    assert result.json()["state"]["status"] == "validated"
    assert result.json()["state"]["result"]["scope_source"] == "not_checked"
    assert result.json()["state"]["result"]["returned_scopes"] == []
    assert captured.events == []
    assert [request.method for request in transport.requests] == ["GET", "GET"]
    assert not [record for record in caplog.records if record.name == "umbod.application.failure"]
    assert "sentinel-client" not in result.text
