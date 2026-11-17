import json
from tests.support.personal_oauth_applications import InMemoryPersonalOAuthApplicationStore, application_clock
import logging
from hashlib import sha256
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi import FastAPI

from tests.support.application_failures import CapturingApplicationFailures
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpRequest, OAuthHttpResponse
from umbod.core.diagnostics import ApplicationFailureKind, CorrelatedFailureContext
from umbod.logging import OpenTelemetryJsonFormatter
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_dependencies import get_personal_oauth_provider
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_diagnostics import get_oauth_application_failures

from .test_personal_oauth_routes import OAuthApi, assert_safe_callback_page, oauth_api as oauth_api


SENTINELS = ("sentinel-description", "sentinel-token", "sentinel-payload", "https://sentinel-private.example")


def response(value: dict[str, object], status: int = 200) -> OAuthHttpResponse:
    return OAuthHttpResponse(status=status, body=json.dumps(value).encode())


def discovery_responses() -> list[OAuthHttpResponse]:
    return [
        response({"resource": "https://tools.example/mcp", "authorization_servers": ["https://issuer.example"]}),
        response({
            "issuer": "https://issuer.example", "authorization_endpoint": "https://issuer.example/authorize",
            "token_endpoint": "https://issuer.example/token", "registration_endpoint": "https://issuer.example/register",
            "code_challenge_methods_supported": ["S256"], "grant_types_supported": ["authorization_code"],
            "response_types_supported": ["code"], "token_endpoint_auth_methods_supported": ["none"],
            "authorization_response_iss_parameter_supported": True,
        }),
    ]


def install_provider(api: OAuthApi, transport: InMemoryOAuthHttpTransport) -> None:
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.LOCAL_DEVELOPMENT, transport, applications=InMemoryPersonalOAuthApplicationStore(application_clock), clock=application_clock)

    def provide() -> DiscoveredPersonalOAuthProvider:
        return provider

    for route in api.app.routes:
        child = getattr(route, "app", None)
        if isinstance(child, FastAPI):
            child.dependency_overrides[get_personal_oauth_provider] = provide


def observe_application(api: OAuthApi) -> CapturingApplicationFailures:
    personal_app = next(route.app for route in api.app.routes if getattr(route, "path", "") == "/api/me")
    channel = personal_app.dependency_overrides[get_oauth_application_failures]()
    captured = CapturingApplicationFailures()
    channel.connect("test.oauth.capture", captured.send)
    return captured


def test_registration_rejection_reaches_public_response_observer_and_correlated_safe_warning(
    oauth_api: OAuthApi, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    transport = InMemoryOAuthHttpTransport(discovery_responses() + [response({
        "error": "invalid_client_metadata", "error_description": "sentinel-description",
        "access_token": "sentinel-token", "payload": "sentinel-payload", "url": "https://sentinel-private.example",
    }, status=403)])
    install_provider(oauth_api, transport)
    captured = observe_application(oauth_api)

    result = oauth_api.client.post(oauth_api.url, headers={"X-Access": "alice", "X-Request-ID": "untrusted-request-id"}, json={})

    assert result.status_code == 502
    assert result.json() == {"detail": {"code": "personal_oauth_provider_failure", "stage": "registration", "reason": "provider_rejected"}}
    assert len(transport.requests) == 3
    assert len(captured.events) == 1
    event = captured.events[0]
    assert event.kind is ApplicationFailureKind.PERSONAL_OAUTH
    assert event.correlation == CorrelatedFailureContext(result.headers["X-Request-ID"], None)
    assert result.headers["X-Request-ID"] != "untrusted-request-id"
    attributes = dict(event.attributes)
    assert attributes["oauth.stage"] == "registration"
    assert attributes["oauth.reason"] == "provider_rejected"
    assert attributes["oauth.downstream.response_received"] is True
    assert attributes["oauth.downstream.http.status_code"] == 403
    assert attributes["connector.id_hash"] == sha256(oauth_api.connector_id.encode()).hexdigest()
    records = [record for record in caplog.records if record.name == "umbod.application.failure"]
    assert len(records) == 1
    payload = json.loads(OpenTelemetryJsonFormatter("test").format(records[0]))
    assert payload["severity_text"] == "WARNING"
    assert payload["trace_id"] == result.headers["X-Request-ID"]
    serialized = result.text + event.model_dump_json() + json.dumps(payload)
    for sentinel in SENTINELS + (oauth_api.connector_id, "https://issuer.example", "https://tools.example/mcp"):
        assert sentinel not in serialized


def test_unexpected_provider_error_is_alertable_without_exposing_exception_details(
    oauth_api: OAuthApi, caplog: pytest.LogCaptureFixture,
) -> None:
    oauth_api.provider.preparation_failures.append(RuntimeError("sentinel-token https://sentinel-private.example"))
    captured = observe_application(oauth_api)

    result = oauth_api.client.post(oauth_api.url, headers={"X-Access": "alice"}, json={})

    assert result.status_code == 502
    assert result.json() == {"detail": {"code": "personal_oauth_provider_failure", "stage": "discovery", "reason": "unexpected_failure"}}
    assert len(captured.events) == 1
    attributes = dict(captured.events[0].attributes)
    assert attributes["failure.origin"] == "internal"
    assert attributes["oauth.reason"] == "unexpected_failure"
    records = [record for record in caplog.records if record.name == "umbod.application.failure"]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    payload = json.loads(OpenTelemetryJsonFormatter("test").format(records[0]))
    assert payload["trace_id"] == result.headers["X-Request-ID"]
    for sentinel in SENTINELS:
        assert sentinel not in result.text + captured.events[0].model_dump_json() + json.dumps(payload)


class TimeoutOAuthTransport(InMemoryOAuthHttpTransport):
    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        self.requests.append(command)
        raise TimeoutError("sentinel-token https://sentinel-private.example")


@pytest.mark.parametrize("timeout,reason,received", [(True, "timeout", False), (False, "invalid_response", True)])
def test_discovery_timeout_and_malformed_response_have_distinct_safe_diagnostics(
    oauth_api: OAuthApi, timeout: bool, reason: str, received: bool,
) -> None:
    transport = TimeoutOAuthTransport([]) if timeout else InMemoryOAuthHttpTransport([
        OAuthHttpResponse(status=200, body=b"sentinel-payload sentinel-token https://sentinel-private.example"),
    ])
    install_provider(oauth_api, transport)
    captured = observe_application(oauth_api)

    result = oauth_api.client.post(oauth_api.url, headers={"X-Access": "alice"}, json={})

    assert result.status_code == (502 if timeout else 422)
    expected_detail = {"code": "personal_oauth_provider_failure", "stage": "discovery", "reason": reason} if timeout else {"code": "personal_oauth_provider_unsupported"}
    assert result.json() == {"detail": expected_detail}
    assert len(captured.events) == 1
    attributes = dict(captured.events[0].attributes)
    assert attributes["oauth.reason"] == reason
    assert attributes["oauth.downstream.response_received"] is received
    if received:
        assert attributes["oauth.downstream.http.status_code"] == 200
    else:
        assert "oauth.downstream.http.status_code" not in attributes
    for sentinel in SENTINELS:
        assert sentinel not in result.text + captured.events[0].model_dump_json()


def test_callback_exchange_rejection_uses_shared_application_channel_and_safe_message(
    oauth_api: OAuthApi, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    transport = InMemoryOAuthHttpTransport(discovery_responses() + [
        response({
            "client_id": "sentinel-client", "token_endpoint_auth_method": "none",
            "redirect_uris": ["http://localhost:18010/api/oauth/downstream-mcp/callback"],
            "grant_types": ["authorization_code"], "response_types": ["code"],
        }),
        response({"error": "invalid_grant", "error_description": "sentinel-description", "access_token": "sentinel-token"}, status=400),
    ])
    install_provider(oauth_api, transport)
    captured = observe_application(oauth_api)
    attempt = oauth_api.start()
    authorization = urlsplit(attempt["authorization_url"])
    query = parse_qs(authorization.query)
    callback = query["redirect_uri"][0] + "?" + urlencode({"state": query["state"][0], "code": "sentinel-code", "iss": "https://issuer.example"})

    result = oauth_api.client.get(callback)

    assert result.status_code == 400
    assert_safe_callback_page(result)
    assert "Sign-in could not be completed" in result.text
    assert "The provider rejected sign-in." in result.text
    assert "Return to the dashboard" in result.text
    assert len(captured.events) == 1
    event = captured.events[0]
    assert event.correlation == CorrelatedFailureContext(result.headers["X-Request-ID"], None)
    attributes = dict(event.attributes)
    assert attributes["oauth.stage"] == "token_exchange"
    assert attributes["oauth.reason"] == "provider_rejected"
    assert attributes["oauth.downstream.http.status_code"] == 400
    assert oauth_api.client.get(oauth_api.url + "/" + attempt["attempt_id"], headers={"X-Access": "alice"}).json()["status"] == "failed"
    serialized = result.text + event.model_dump_json() + caplog.text
    for sentinel in SENTINELS + ("sentinel-code", "sentinel-client", query["state"][0]):
        assert sentinel not in serialized
