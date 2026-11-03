import json
from urllib.parse import parse_qs, urlsplit

import pytest
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import PresentCallbackIssuer

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy, validate_callback_url
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.validation import AuthorizationServer, validated_url
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported, PreparePersonalOAuth
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration.models import PersonalOAuthClient
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import DynamicPublicOAuthClient, PersonalOAuthPolicy, PreconfiguredConfidentialOAuthClient, PreconfiguredPublicOAuthClient

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import issuer_callback_uri

from .conftest import ProviderCase, exchange_command, response


LOOPBACK_CALLBACKS = (
    "http://localhost:18010/api/oauth/downstream-mcp/callback",
    "http://127.0.0.1/callback",
    "http://[::1]:65535/callback",
    "http://localhost",
)


@pytest.mark.parametrize("uri", LOOPBACK_CALLBACKS)
def test_http_callback_requires_local_policy_and_never_becomes_outbound_destination(uri: str) -> None:
    validate_callback_url(uri, CallbackURLPolicy.LOCAL_DEVELOPMENT)
    with pytest.raises(ValueError):
        validate_callback_url(uri, CallbackURLPolicy.STRICT)
    with pytest.raises(ValueError):
        validated_url(uri)


@pytest.mark.parametrize("uri", (
    "http://localhost.evil/callback", "http://evil.localhost/callback", "http://LOCALHOST/callback",
    "http://127.1/callback", "http://2130706433/callback", "http://0177.0.0.1/callback",
    "http://0x7f000001/callback", "http://127.000.000.001/callback", "http://127.0.0.2/callback",
    "http://[0:0:0:0:0:0:0:1]/callback", "http://[::ffff:127.0.0.1]/callback",
    "http://localhost./callback", "http://%6cocalhost/callback", "http://localhost%2e/callback",
    "http://user@localhost/callback", "http://user:secret@localhost/callback",
    "http://localhost:0/callback", "http://localhost:65536/callback", "http://localhost:-1/callback",
    "http://localhost:/callback", "http://localhost:abc/callback", "http://localhost:80:90/callback",
    "http://[::1/callback", "http:///localhost/callback", "http:localhost/callback",
    "http://localhost/callback?", "http://localhost/callback?code=evil", "http://localhost/callback#",
    "http://localhost\\@evil/callback", "http://localhost/call\\back", "http://localhost/%5cpath",
    "http://localhost/\ncallback", "http://localhost/%0dcallback", "http://localhost/%7fcallback",
    "http://localhost/é", "http://localhost/%C3%A9", " http://localhost/callback",
    "http://10.0.0.1/callback", "http://public.example/callback",
))
@pytest.mark.parametrize("policy", tuple(CallbackURLPolicy))
def test_callback_policy_rejects_nonliteral_or_unsafe_http_urls(uri: str, policy: CallbackURLPolicy) -> None:
    with pytest.raises(ValueError):
        validate_callback_url(uri, policy)


@pytest.mark.parametrize("policy", tuple(CallbackURLPolicy))
def test_https_callback_keeps_existing_validation(policy: CallbackURLPolicy) -> None:
    validate_callback_url("https://umbod.example/callback", policy)
    with pytest.raises(ValueError):
        validate_callback_url("https://127.0.0.1/callback", policy)


def client_preparation(preparation: PreparePersonalOAuth, method: str) -> PreparePersonalOAuth:
    client: PersonalOAuthClient = DynamicPublicOAuthClient()
    if method == "none":
        client = PreconfiguredPublicOAuthClient(issuer_url="https://issuer.example/tenant", client_id="configured")
    elif method != "dynamic":
        client = PreconfiguredConfidentialOAuthClient.model_validate({
            "issuer_url": "https://issuer.example/tenant", "client_id": "configured", "client_secret": "secret",
            "token_endpoint_auth_method": method,
        })
    return preparation.model_copy(update={"policy": PersonalOAuthPolicy(revision="policy", requested_scopes=(), client=client)})


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [
    (method, uri)
    for uri in LOOPBACK_CALLBACKS
    for method in ("dynamic", "none", "client_secret_basic", "client_secret_post")
])
async def test_local_http_callback_prepares_and_exchanges_with_exact_saved_binding(
    provider_case: ProviderCase, case: tuple[str, str],
) -> None:
    preparation = provider_case.preparation
    resource_metadata = provider_case.resource_metadata
    server_metadata = provider_case.server_metadata
    client_metadata = provider_case.client_metadata
    method, uri = case
    preparation = client_preparation(preparation.model_copy(update={"redirect_uri": uri}), method)
    server_metadata.pop("authorization_response_iss_parameter_supported")
    server_metadata["token_endpoint_auth_methods_supported"] = ["none" if method == "dynamic" else method]
    final_uri = issuer_callback_uri(uri, str(server_metadata["issuer"]))
    client_metadata["redirect_uris"] = [final_uri]
    responses = [response(resource_metadata), response(server_metadata)]
    if method == "dynamic":
        responses.append(response(client_metadata))
    transport = InMemoryOAuthHttpTransport(responses)
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.LOCAL_DEVELOPMENT, transport)
    prepared = await provider.prepare(preparation)
    assert parse_qs(urlsplit(prepared.authorization_url.get_secret_value()).query)["redirect_uri"] == [final_uri]
    assert json.loads(prepared.context.get_secret_value())["redirect_uri"] == final_uri
    if method == "dynamic":
        registration = json.loads(transport.requests[-1].body.get_secret_value())
        assert registration["client_name"] == "Umbod"
        assert registration["application_type"] == "native"
    exchange_transport = InMemoryOAuthHttpTransport([response({"access_token": "access", "token_type": "Bearer"})])
    strict: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, exchange_transport)
    with pytest.raises(PersonalOAuthProviderFailure):
        await strict.exchange(exchange_command(preparation, prepared))
    assert not exchange_transport.requests
    resumed: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.LOCAL_DEVELOPMENT, exchange_transport)
    await resumed.exchange(exchange_command(preparation, prepared))
    assert len(exchange_transport.requests) == 1
    assert parse_qs(exchange_transport.requests[0].body.get_secret_value())["redirect_uri"] == [final_uri]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [
    (uri, application_type, echo)
    for echo in ("matching", "mismatching", "missing", "null", "wrong_type")
    for uri, application_type in (
        ("http://localhost:18010/api/oauth/downstream-mcp/callback", "native"),
        ("https://umbod.example/api/oauth/downstream-mcp/callback", "web"),
    )
])
async def test_registration_application_type_echo_is_bound_when_present(
    provider_case: ProviderCase, case: tuple[str, str, str],
) -> None:
    preparation = provider_case.preparation
    resource_metadata = provider_case.resource_metadata
    server_metadata = provider_case.server_metadata
    client_metadata = provider_case.client_metadata
    uri, application_type, echo = case
    preparation = preparation.model_copy(update={"redirect_uri": uri})
    client_metadata["redirect_uris"] = [uri]
    client_metadata["client_name"] = "Provider display name"
    if echo != "missing":
        client_metadata["application_type"] = {
            "matching": application_type,
            "mismatching": "web" if application_type == "native" else "native",
            "null": None, "wrong_type": 1,
        }[echo]
    transport = InMemoryOAuthHttpTransport([response(resource_metadata), response(server_metadata), response(client_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.LOCAL_DEVELOPMENT, transport)
    if echo in ("matching", "missing"):
        await provider.prepare(preparation)
    else:
        with pytest.raises(PersonalOAuthProviderUnsupported):
            await provider.prepare(preparation)
    assert len(transport.requests) == 3
    registration = json.loads(transport.requests[-1].body.get_secret_value())
    assert registration["application_type"] == application_type
    assert registration["client_name"] == "Umbod"
    assert registration["redirect_uris"] == [uri]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("dynamic", "none", "client_secret_basic", "client_secret_post"))
async def test_strict_http_callback_rejected_before_provider_contact(preparation: PreparePersonalOAuth, method: str) -> None:
    preparation = client_preparation(preparation.model_copy(update={"redirect_uri": LOOPBACK_CALLBACKS[0]}), method)
    transport = InMemoryOAuthHttpTransport([])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)
    assert not transport.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ("authorization_endpoint", "token_endpoint", "registration_endpoint"))
@pytest.mark.parametrize("url", ("http://localhost:18010/endpoint", "https://127.0.0.1/endpoint", "https://[::1]/endpoint"))
async def test_local_callback_policy_does_not_relax_discovered_outbound_destinations(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object], server_metadata: dict[str, object],
    field: str, url: str,
) -> None:
    preparation = preparation.model_copy(update={"redirect_uri": LOOPBACK_CALLBACKS[0]})
    server_metadata[field] = url
    transport = InMemoryOAuthHttpTransport([response(resource_metadata), response(server_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.LOCAL_DEVELOPMENT, transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)
    assert len(transport.requests) == 2
    assert all(request.method == "GET" for request in transport.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("advertisement", ("omitted", "true", "false", "null", "string", "integer"))
async def test_issuer_advertisement_selects_bound_or_generic_callback_and_rejects_invalid_flags(
    provider_case: ProviderCase, advertisement: str,
) -> None:
    preparation = provider_case.preparation
    resource_metadata = provider_case.resource_metadata
    server_metadata = provider_case.server_metadata
    client_metadata = provider_case.client_metadata
    field = "authorization_response_iss_parameter_supported"
    server_metadata.pop(field)
    if advertisement != "omitted":
        server_metadata[field] = {"true": True, "false": False, "null": None, "string": "true", "integer": 1}[advertisement]
    if advertisement in ("omitted", "false"):
        client_metadata["redirect_uris"] = [issuer_callback_uri(preparation.redirect_uri, str(server_metadata["issuer"]))]
    transport = InMemoryOAuthHttpTransport([response(resource_metadata), response(server_metadata), response(client_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport)
    if advertisement not in ("omitted", "true", "false"):
        with pytest.raises(PersonalOAuthProviderUnsupported):
            await provider.prepare(preparation)
        assert len(transport.requests) == 2
        return
    server = AuthorizationServer.model_validate(server_metadata)
    assert (field in server.model_fields_set) is (advertisement != "omitted")
    assert server.authorization_response_iss_parameter_supported is (advertisement == "true")
    await provider.prepare(preparation)
    assert len(transport.requests) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer", ("", "https://wrong.example", "https://ISSUER.example/tenant", "https://issuer.example/tenant/", "https://issuer.example:443/tenant", "https://issuer.example/%74enant"))
@pytest.mark.parametrize("advertisement", ("omitted", "true"))
async def test_unknown_or_advertised_issuer_support_never_weakens_actual_issuer_binding(
    provider_case: ProviderCase, issuer: str, advertisement: str,
) -> None:
    preparation = provider_case.preparation
    resource_metadata = provider_case.resource_metadata
    server_metadata = provider_case.server_metadata
    client_metadata = provider_case.client_metadata
    if advertisement == "omitted":
        server_metadata.pop("authorization_response_iss_parameter_supported")
        client_metadata["redirect_uris"] = [issuer_callback_uri(preparation.redirect_uri, str(server_metadata["issuer"]))]
    transport = InMemoryOAuthHttpTransport([response(resource_metadata), response(server_metadata), response(client_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport)
    prepared = await provider.prepare(preparation)
    command = exchange_command(preparation, prepared).model_copy(update={"issuer": PresentCallbackIssuer.model_construct(kind="present", value=issuer)})
    with pytest.raises(PersonalOAuthProviderFailure):
        await provider.exchange(command)
    assert not [request for request in transport.requests if request.url.endswith("/token")]
