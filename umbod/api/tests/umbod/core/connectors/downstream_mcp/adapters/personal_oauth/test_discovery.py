from urllib.parse import parse_qs, urlsplit

import httpcore
import pytest

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.discovery import authorization_server_metadata_urls
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.setup import DiscoveredPersonalOAuthSetupProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpRequest, OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthPolicy, PreconfiguredPublicOAuthClient
from umbod.core.connectors.downstream_mcp.personal_oauth_setup.models import DiscoverPersonalOAuthSetup, ValidatePersonalOAuthSetup, ValidatedPersonalOAuthSetup
from umbod.core.invocation.diagnostics import DownstreamHttpResponse, NoDownstreamResponse

from .conftest import ProviderCase, response


ISSUER = "https://issuer.example/tenant"
RESOURCE_METADATA_URL = "https://resource.example/.well-known/oauth-protected-resource/mcp"
METADATA_URLS = (
    "https://issuer.example/.well-known/oauth-authorization-server/tenant",
    "https://issuer.example/.well-known/openid-configuration/tenant",
    "https://issuer.example/tenant/.well-known/openid-configuration",
)
SENTINEL = "private-provider-response-sentinel"


def _not_found() -> OAuthHttpResponse:
    return OAuthHttpResponse(status=404, body=SENTINEL.encode())


@pytest.mark.parametrize("issuer,paths", [
    ("https://issuer.example", ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration")),
    ("https://issuer.example/", ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration")),
    ("https://issuer.example/tenant", ("/.well-known/oauth-authorization-server/tenant", "/.well-known/openid-configuration/tenant", "/tenant/.well-known/openid-configuration")),
    ("https://issuer.example/tenant/", ("/.well-known/oauth-authorization-server/tenant", "/.well-known/openid-configuration/tenant", "/tenant/.well-known/openid-configuration")),
    ("https://issuer.example:8443/org/tenant/", ("/.well-known/oauth-authorization-server/org/tenant", "/.well-known/openid-configuration/org/tenant", "/org/tenant/.well-known/openid-configuration")),
])
def test_metadata_urls_preserve_origin_and_order_without_duplicate_root_fallback(issuer: str, paths: tuple[str, ...]) -> None:
    origin = urlsplit(issuer)
    assert authorization_server_metadata_urls(origin) == tuple(f"{origin.scheme}://{origin.netloc}{path}" for path in paths)


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback_count", [0, 1, 2], ids=["oauth-priority", "openid-prefix", "openid-suffix"])
async def test_prepare_uses_first_available_metadata_and_registers_once(provider_case: ProviderCase, fallback_count: int) -> None:
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), *[_not_found() for _ in range(fallback_count)],
        response(provider_case.server_metadata), response(provider_case.client_metadata),
    ])
    prepared = await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport).prepare(provider_case.preparation)
    assert parse_qs(urlsplit(prepared.authorization_url.get_secret_value()).query)["client_id"] == ["public-client"]
    assert [(request.method, request.url) for request in transport.requests] == [
        ("GET", RESOURCE_METADATA_URL), *[("GET", url) for url in METADATA_URLS[:fallback_count + 1]],
        ("POST", "https://issuer.example/register"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback_count", [1, 2])
async def test_setup_discover_reports_openid_scopes_without_approving_or_registering(provider_case: ProviderCase, fallback_count: int) -> None:
    provider_case.resource_metadata["scopes_supported"] = ["read"]
    provider_case.server_metadata["scopes_supported"] = ["write", "read"]
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), *[_not_found() for _ in range(fallback_count)], response(provider_case.server_metadata),
    ])
    command = DiscoverPersonalOAuthSetup(
        endpoint_url=provider_case.preparation.endpoint_url, redirect_uri=provider_case.preparation.redirect_uri,
        policy=provider_case.preparation.policy,
    )
    discovered = await DiscoveredPersonalOAuthSetupProvider(CallbackURLPolicy.STRICT, transport).discover(command)
    assert discovered.issuer_url == ISSUER
    assert discovered.available_scopes == ("read", "write")
    assert command.policy.requested_scopes == ()
    assert [(request.method, request.url) for request in transport.requests] == [
        ("GET", RESOURCE_METADATA_URL), *[("GET", url) for url in METADATA_URLS[:fallback_count + 1]],
    ]


@pytest.mark.asyncio
async def test_prepare_does_not_request_openid_advertised_scopes(provider_case: ProviderCase) -> None:
    provider_case.server_metadata["scopes_supported"] = ["read", "write"]
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), _not_found(), response(provider_case.server_metadata), response(provider_case.client_metadata),
    ])
    prepared = await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport).prepare(provider_case.preparation)
    assert "scope" not in parse_qs(urlsplit(prepared.authorization_url.get_secret_value()).query)
    assert '"scope"' not in transport.requests[-1].body.get_secret_value()
    assert provider_case.preparation.policy.requested_scopes == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("static", [False, True], ids=["dynamic", "static"])
async def test_setup_validate_openid_without_registration_endpoint_requires_static_client(provider_case: ProviderCase, static: bool) -> None:
    provider_case.server_metadata.pop("registration_endpoint")
    policy = PersonalOAuthPolicy(
        revision="static", requested_scopes=(), client=PreconfiguredPublicOAuthClient(issuer_url=ISSUER, client_id="existing-client"),
    ) if static else provider_case.preparation.policy
    command = ValidatePersonalOAuthSetup(
        endpoint_url=provider_case.preparation.endpoint_url, redirect_uri=provider_case.preparation.redirect_uri, policy=policy,
    )
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), _not_found(), response(provider_case.server_metadata)])
    provider = DiscoveredPersonalOAuthSetupProvider(CallbackURLPolicy.STRICT, transport)
    if static:
        result = await provider.validate(command)
        assert isinstance(result, ValidatedPersonalOAuthSetup)
        assert result.discovery.registration_mode == "preconfigured_public"
        assert result.scope_source == "not_checked"
    else:
        with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
            await provider.validate(command)
        assert caught.value.evidence.reason == "registration_unavailable"
    assert [(request.method, request.url) for request in transport.requests] == [
        ("GET", RESOURCE_METADATA_URL), ("GET", METADATA_URLS[0]), ("GET", METADATA_URLS[1]),
    ]


@pytest.mark.asyncio
async def test_setup_validate_registers_once_after_openid_fallback(provider_case: ProviderCase) -> None:
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), _not_found(), _not_found(),
        response(provider_case.server_metadata), response(provider_case.client_metadata),
    ])
    result = await DiscoveredPersonalOAuthSetupProvider(CallbackURLPolicy.STRICT, transport).validate(ValidatePersonalOAuthSetup(
        endpoint_url=provider_case.preparation.endpoint_url, redirect_uri=provider_case.preparation.redirect_uri,
        policy=provider_case.preparation.policy,
    ))
    assert isinstance(result, ValidatedPersonalOAuthSetup)
    assert [(request.method, request.url) for request in transport.requests] == [
        ("GET", RESOURCE_METADATA_URL), *[("GET", url) for url in METADATA_URLS], ("POST", "https://issuer.example/register"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value,reason", [
    ("issuer", ISSUER + "/", "issuer_mismatch"),
    ("code_challenge_methods_supported", ["plain"], "pkce_s256_required"),
    ("code_challenge_methods_supported", [], "pkce_s256_required"),
    ("authorization_endpoint", "http://issuer.example/authorize", "invalid_response"),
])
async def test_invalid_openid_capabilities_or_security_never_try_later_metadata(provider_case: ProviderCase, field: str, value: object, reason: str) -> None:
    provider_case.server_metadata[field] = value
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), _not_found(), response(provider_case.server_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport).prepare(provider_case.preparation)
    assert caught.value.evidence.reason == reason
    assert [request.url for request in transport.requests] == [RESOURCE_METADATA_URL, *METADATA_URLS[:2]]


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback_count", [0, 1])
@pytest.mark.parametrize("body", [SENTINEL.encode(), b'{}'], ids=["malformed-json", "missing-fields"])
async def test_invalid_metadata_body_never_triggers_fallback(provider_case: ProviderCase, fallback_count: int, body: bytes) -> None:
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), *[_not_found() for _ in range(fallback_count)], OAuthHttpResponse(status=200, body=body),
    ])
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport).prepare(provider_case.preparation)
    assert caught.value.evidence.reason == "invalid_response"
    assert caught.value.evidence.downstream_response == DownstreamHttpResponse(status_code=200)
    assert SENTINEL not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert [request.url for request in transport.requests] == [RESOURCE_METADATA_URL, *METADATA_URLS[:fallback_count + 1]]


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback_count", [0, 1])
@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 429, 500, 503])
async def test_non404_metadata_rejection_stops_discovery(provider_case: ProviderCase, fallback_count: int, status: int) -> None:
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), *[_not_found() for _ in range(fallback_count)], OAuthHttpResponse(status=status, body=SENTINEL.encode()),
    ])
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport).prepare(provider_case.preparation)
    assert caught.value.evidence.stage == "discovery"
    assert caught.value.evidence.reason == "provider_rejected"
    assert caught.value.evidence.downstream_response == DownstreamHttpResponse(status_code=status)
    assert SENTINEL not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert [request.url for request in transport.requests] == [RESOURCE_METADATA_URL, *METADATA_URLS[:fallback_count + 1]]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 403, 503])
async def test_final_fallback_rejection_preserves_final_status_without_body(provider_case: ProviderCase, status: int) -> None:
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), _not_found(), _not_found(), OAuthHttpResponse(status=status, body=SENTINEL.encode()),
    ])
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport).prepare(provider_case.preparation)
    assert caught.value.evidence.model_dump() == {
        "stage": "discovery", "reason": "provider_rejected", "downstream_response": {"kind": "http_response", "status_code": status},
    }
    assert SENTINEL not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert [request.url for request in transport.requests] == [RESOURCE_METADATA_URL, *METADATA_URLS]


class InterruptedMetadataTransport(InMemoryOAuthHttpTransport):
    def __init__(self, responses: list[OAuthHttpResponse], error: Exception) -> None:
        super().__init__(responses)
        self.error = error

    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        if self.responses:
            return await super().request(command)
        self.requests.append(command)
        raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback_count", [0, 1])
@pytest.mark.parametrize("error,reason", [(TimeoutError(SENTINEL), "timeout"), (httpcore.ConnectError(SENTINEL), "network_failure")])
async def test_metadata_transport_failure_does_not_advance_or_expose_error(provider_case: ProviderCase, fallback_count: int, error: Exception, reason: str) -> None:
    transport = InterruptedMetadataTransport([response(provider_case.resource_metadata), *[_not_found() for _ in range(fallback_count)]], error)
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport).prepare(provider_case.preparation)
    assert caught.value.evidence.stage == "discovery"
    assert caught.value.evidence.reason == reason
    assert caught.value.evidence.downstream_response == NoDownstreamResponse()
    assert SENTINEL not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert [request.url for request in transport.requests] == [RESOURCE_METADATA_URL, *METADATA_URLS[:fallback_count + 1]]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 503])
async def test_registration_rejection_after_openid_discovery_does_not_retry_registration_or_metadata(provider_case: ProviderCase, status: int) -> None:
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), _not_found(), response(provider_case.server_metadata), OAuthHttpResponse(status=status, body=SENTINEL.encode()),
    ])
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport).prepare(provider_case.preparation)
    assert caught.value.evidence.stage == "registration"
    assert caught.value.evidence.downstream_response == DownstreamHttpResponse(status_code=status)
    assert SENTINEL not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert [(request.method, request.url) for request in transport.requests] == [
        ("GET", RESOURCE_METADATA_URL), ("GET", METADATA_URLS[0]), ("GET", METADATA_URLS[1]), ("POST", "https://issuer.example/register"),
    ]
