import pytest
from tests.support.personal_oauth_applications import InMemoryPersonalOAuthApplicationStore, application_clock

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.metadata import DiscoveredPersonalOAuthMetadataProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.setup import DiscoveredPersonalOAuthSetupProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import DynamicPublicOAuthClient, PersonalOAuthPolicy
from umbod.core.connectors.downstream_mcp.personal_oauth_metadata import DiscoverPersonalOAuthMetadata
from umbod.core.connectors.downstream_mcp.personal_oauth_setup.models import DiscoverPersonalOAuthSetup

from .conftest import ProviderCase, exchange_command, response


ISSUER = "https://issuer.example/tenant"
ENDPOINT = "https://resource.example/mcp"


def command(selection: dict[str, str]) -> DiscoverPersonalOAuthMetadata:
    return DiscoverPersonalOAuthMetadata.model_validate({"endpoint_url": ENDPOINT, "issuer_selection": selection})


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_scopes,server_scopes,expected,source", [
    ({}, {}, (), "unavailable"),
    ({}, {"scopes_supported": ["write", "read"]}, ("read", "write"), "authorization_server"),
    ({"scopes_supported": []}, {"scopes_supported": ["read"]}, (), "resource"),
    ({"scopes_supported": ["read"]}, {"scopes_supported": ["write"]}, ("read",), "resource"),
])
async def test_preview_scope_preference_and_get_only(provider_case: ProviderCase, resource_scopes: dict[str, object], server_scopes: dict[str, object], expected: tuple[str, ...], source: str) -> None:
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata | resource_scopes), response(provider_case.server_metadata | server_scopes),
    ])
    result = await DiscoveredPersonalOAuthMetadataProvider(transport).discover(command({"kind": "automatic"}))
    assert result.kind == "discovered"
    assert result.available_scopes == expected
    assert result.scope_source == source
    assert result.automatic_registration == "available"
    assert [request.method for request in transport.requests] == ["GET", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize("registration,methods", [(False, ["none"]), (True, ["unsupported"]), (False, ["client_secret_basic"])])
async def test_preview_retains_metadata_when_automatic_registration_unavailable(provider_case: ProviderCase, registration: bool, methods: list[str]) -> None:
    if not registration:
        provider_case.server_metadata.pop("registration_endpoint")
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = methods
    provider_case.server_metadata["scopes_supported"] = ["read"]
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    result = await DiscoveredPersonalOAuthMetadataProvider(transport).discover(command({"kind": "automatic"}))
    assert result.kind == "discovered"
    assert result.automatic_registration == "unavailable"
    assert result.available_scopes == ("read",)
    assert result.token_endpoint_auth_methods == tuple(methods)
    assert len(transport.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("methods,kind,method", [
    (["none", "client_secret_basic"], "dynamic_public", ""),
    (["client_secret_post", "client_secret_basic"], "dynamic_confidential", "client_secret_basic"),
    (["client_secret_post"], "dynamic_confidential", "client_secret_post"),
    (["private_key_jwt"], "unavailable", ""),
])
async def test_preview_proposes_supported_automatic_client_with_safe_preference(provider_case: ProviderCase, methods: list[str], kind: str, method: str) -> None:
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = methods
    result = await DiscoveredPersonalOAuthMetadataProvider(InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
    ])).discover(command({"kind": "automatic"}))
    assert result.kind == "discovered"
    assert result.automatic_client.kind == kind
    if result.automatic_client.kind == "dynamic_confidential":
        assert result.automatic_client.token_endpoint_auth_method == method
        assert result.automatic_client.approved_issuers == (ISSUER,)
    assert "client_secret" not in result.automatic_client.model_dump()


@pytest.mark.asyncio
async def test_preview_requires_explicit_multiple_issuer_choice(provider_case: ProviderCase) -> None:
    issuers = ["https://other.example", ISSUER]
    provider_case.resource_metadata["authorization_servers"] = issuers
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata)])
    result = await DiscoveredPersonalOAuthMetadataProvider(transport).discover(command({"kind": "automatic"}))
    assert result.kind == "issuer_selection_required"
    assert result.issuer_urls == tuple(issuers)
    assert len(transport.requests) == 1


@pytest.mark.asyncio
async def test_preview_selects_only_exact_advertised_issuer(provider_case: ProviderCase) -> None:
    provider_case.resource_metadata["authorization_servers"] = ["https://other.example", ISSUER]
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    result = await DiscoveredPersonalOAuthMetadataProvider(transport).discover(command({"kind": "selected", "issuer_url": ISSUER}))
    assert result.kind == "discovered"
    assert result.issuer_url == ISSUER
    assert "issuer.example" in transport.requests[-1].url


@pytest.mark.asyncio
async def test_preview_refuses_unadvertised_issuer_before_fetch(provider_case: ProviderCase) -> None:
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await DiscoveredPersonalOAuthMetadataProvider(transport).discover(command({"kind": "selected", "issuer_url": ISSUER + "/"}))
    assert caught.value.evidence.reason == "issuer_mismatch"
    assert len(transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["authorization_endpoint", "token_endpoint", "registration_endpoint"])
async def test_preview_refuses_unsafe_advertised_destination(provider_case: ProviderCase, field: str) -> None:
    provider_case.server_metadata[field] = "https://127.0.0.1/private-secret"
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await DiscoveredPersonalOAuthMetadataProvider(transport).discover(command({"kind": "automatic"}))
    assert "private-secret" not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert all(request.method == "GET" for request in transport.requests)


@pytest.mark.asyncio
async def test_preview_preserves_openid_404_only_fallback(provider_case: ProviderCase) -> None:
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), OAuthHttpResponse(status=404, body=b"secret"), response(provider_case.server_metadata),
    ])
    result = await DiscoveredPersonalOAuthMetadataProvider(transport).discover(command({"kind": "automatic"}))
    assert result.kind == "discovered"
    assert "openid-configuration" in transport.requests[-1].url
    assert len(transport.requests) == 3


@pytest.mark.asyncio
async def test_preview_provider_failure_is_sanitized_and_never_falls_back(provider_case: ProviderCase) -> None:
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), OAuthHttpResponse(status=503, body=b"private-secret")])
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await DiscoveredPersonalOAuthMetadataProvider(transport).discover(command({"kind": "automatic"}))
    assert caught.value.evidence.reason == "provider_rejected"
    assert "private-secret" not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert len(transport.requests) == 2


@pytest.mark.asyncio
async def test_prepare_uses_approved_issuer_even_when_multiple_advertised(provider_case: ProviderCase) -> None:
    provider_case.resource_metadata["authorization_servers"] = ["https://other.example", ISSUER]
    policy = PersonalOAuthPolicy(revision="bound", requested_scopes=(), client=DynamicPublicOAuthClient(approved_issuers=(ISSUER,)))
    preparation = provider_case.preparation.model_copy(update={"policy": policy})
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata), response(provider_case.client_metadata)])
    result = await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, applications=InMemoryPersonalOAuthApplicationStore(application_clock), clock=application_clock).prepare(preparation)
    assert result.callback_binding.expected_issuer == ISSUER
    assert transport.requests[-1].method == "POST"


@pytest.mark.asyncio
async def test_prepare_refuses_changed_approved_issuer_before_registration(provider_case: ProviderCase) -> None:
    policy = PersonalOAuthPolicy(revision="bound", requested_scopes=(), client=DynamicPublicOAuthClient(approved_issuers=("https://previous.example",)))
    preparation = provider_case.preparation.model_copy(update={"policy": policy})
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, applications=InMemoryPersonalOAuthApplicationStore(application_clock), clock=application_clock).prepare(preparation)
    assert caught.value.evidence.reason == "issuer_mismatch"
    assert len(transport.requests) == 1


@pytest.mark.asyncio
async def test_saved_setup_discovery_uses_approved_issuer_when_multiple_are_advertised(provider_case: ProviderCase) -> None:
    provider_case.resource_metadata["authorization_servers"] = ["https://other.example", ISSUER]
    policy = PersonalOAuthPolicy(revision="bound", requested_scopes=(), client=DynamicPublicOAuthClient(approved_issuers=(ISSUER,)))
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    result = await DiscoveredPersonalOAuthSetupProvider(CallbackURLPolicy.STRICT, transport).discover(DiscoverPersonalOAuthSetup(
        endpoint_url=ENDPOINT, redirect_uri=provider_case.preparation.redirect_uri, policy=policy,
    ))
    assert result.issuer_url == ISSUER
    assert policy.client.approved_issuers == (ISSUER,)
    assert [request.method for request in transport.requests] == ["GET", "GET"]


@pytest.mark.asyncio
async def test_saved_setup_discovery_refuses_to_replace_disappeared_approved_issuer(provider_case: ProviderCase) -> None:
    policy = PersonalOAuthPolicy(revision="bound", requested_scopes=(), client=DynamicPublicOAuthClient(approved_issuers=("https://previous.example",)))
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await DiscoveredPersonalOAuthSetupProvider(CallbackURLPolicy.STRICT, transport).discover(DiscoverPersonalOAuthSetup(
            endpoint_url=ENDPOINT, redirect_uri=provider_case.preparation.redirect_uri, policy=policy,
        ))
    assert caught.value.evidence.reason == "issuer_mismatch"
    assert policy.client.approved_issuers == ("https://previous.example",)
    assert len(transport.requests) == 1


@pytest.mark.asyncio
async def test_exchange_refuses_context_outside_approved_issuer_before_post(provider_case: ProviderCase) -> None:
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata), response(provider_case.client_metadata)])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, applications=InMemoryPersonalOAuthApplicationStore(application_clock), clock=application_clock)
    prepared = await provider.prepare(provider_case.preparation)
    policy = provider_case.preparation.policy.model_copy(update={"client": DynamicPublicOAuthClient(approved_issuers=("https://replacement.example",))})
    preparation = provider_case.preparation.model_copy(update={"policy": policy})
    with pytest.raises(PersonalOAuthProviderFailure):
        await provider.exchange(exchange_command(preparation, prepared))
    assert len(transport.requests) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("issuers", [
    ["https://issuer.example/" + "x" * 4096],
    ["https://127.0.0.1/private-secret"],
    [ISSUER, ISSUER],
    ["https://issuer.example/" + str(index) for index in range(17)],
])
async def test_preview_refuses_invalid_or_unbounded_advertised_issuers(provider_case: ProviderCase, issuers: list[str]) -> None:
    provider_case.resource_metadata["authorization_servers"] = issuers
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await DiscoveredPersonalOAuthMetadataProvider(transport).discover(command({"kind": "automatic"}))
    assert len(transport.requests) == 1


def test_legacy_dynamic_client_serialization_preserves_old_fingerprint_input() -> None:
    assert DynamicPublicOAuthClient().model_dump() == {"kind": "dynamic_public"}
    assert DynamicPublicOAuthClient().model_dump_json() == '{"kind":"dynamic_public"}'
    bound = DynamicPublicOAuthClient(approved_issuers=(ISSUER,))
    assert DynamicPublicOAuthClient.model_validate_json(bound.model_dump_json()) == bound
    assert bound != DynamicPublicOAuthClient()
