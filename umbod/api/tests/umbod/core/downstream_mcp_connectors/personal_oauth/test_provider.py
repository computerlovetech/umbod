import json
from datetime import timedelta

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import PersonalOAuthGrant, ExpiringPersonalToken
from urllib.parse import parse_qs, urlsplit

import pytest
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import PresentCallbackIssuer
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import (
    InMemoryOAuthHttpTransport,
    OAuthHttpResponse,
    OAuthHttpTransport,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import (
    PersonalOAuthProviderFailure,
    PersonalOAuthProviderUnsupported,
    PreparePersonalOAuth,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthProvider

from .conftest import exchange_command, response


@pytest.mark.asyncio
async def test_preparation_and_exchange_resume_with_only_persisted_context(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object],
    server_metadata: dict[str, object], client_metadata: dict[str, object],
) -> None:
    transport = InMemoryOAuthHttpTransport(responses=[response(resource_metadata), response(server_metadata), response(client_metadata)])
    port: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    prepared = await port.prepare(preparation)
    query = parse_qs(urlsplit(prepared.authorization_url.get_secret_value()).query)
    assert query == {
        "response_type": ["code"], "client_id": ["public-client"], "redirect_uri": [preparation.redirect_uri],
        "state": ["opaque-state"], "code_challenge": ["ZtNPunH49FD35FWYhT5Tv8I7vRKQJ8uxMaL0_9eHjNA"],
        "code_challenge_method": ["S256"], "resource": [preparation.endpoint_url],
    }
    assert transport.requests[0].url == "https://resource.example/.well-known/oauth-protected-resource/mcp"
    assert transport.requests[1].url == "https://issuer.example/.well-known/oauth-authorization-server/tenant"
    assert [destination.url for destination in transport.destinations] == ["https://issuer.example/authorize"]
    registration = json.loads(transport.requests[2].body.get_secret_value())
    assert registration == {
        "client_name": "Umbod", "application_type": "web",
        "redirect_uris": [preparation.redirect_uri], "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code"], "response_types": ["code"],
    }
    exchange_transport = InMemoryOAuthHttpTransport(responses=[response({
        "access_token": "actual-access", "refresh_token": "actual-refresh", "token_type": "bEaReR",
        "expires_in": 3600, "untrusted_extra": "must-not-persist",
    })])
    resumed: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=exchange_transport)
    command = exchange_command(preparation, prepared)
    authorized = await resumed.exchange(command)
    stored = json.loads(authorized.authorization.get_secret_value())
    assert stored["access_token"] == "actual-access"
    assert stored["refresh_token"] == {"kind": "present", "token": "actual-refresh"}
    assert stored["token_type"] == "Bearer"
    grant = PersonalOAuthGrant.model_validate_json(authorized.authorization.get_secret_value())
    assert grant.version == 2
    assert grant.key == command.attempt.query.key
    assert grant.issued_at == command.attempt.query.now
    assert isinstance(grant.lifetime, ExpiringPersonalToken)
    assert grant.lifetime.expires_at == command.attempt.query.now + timedelta(seconds=3600)
    assert "actual-access" not in grant.model_dump_json()
    assert "actual-refresh" not in grant.model_dump_json()
    assert "untrusted_extra" not in stored
    assert "**********" not in authorized.authorization.get_secret_value()
    token_request = parse_qs(exchange_transport.requests[0].body.get_secret_value())
    assert token_request == {
        "grant_type": ["authorization_code"], "code": ["authorization-code"],
        "client_id": ["public-client"], "redirect_uri": [preparation.redirect_uri],
        "code_verifier": ["a" * 43], "resource": [preparation.endpoint_url],
    }
    assert len(exchange_transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 302])
async def test_resource_fallback_is_not_used_except_for_not_found(preparation: PreparePersonalOAuth, status: int) -> None:
    transport = InMemoryOAuthHttpTransport(responses=[OAuthHttpResponse(status=status, body=b"{}")])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)
    assert len(transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 500, 503, 599])
@pytest.mark.parametrize("stage", ["resource", "resource_root", "issuer", "registration"])
async def test_temporary_provider_outages_fail_without_fallback_retry_or_sensitive_details(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object],
    server_metadata: dict[str, object], status: int, stage: str,
) -> None:
    prefixes: dict[str, list[OAuthHttpResponse]] = {
        "resource": [],
        "resource_root": [OAuthHttpResponse(status=404, body=b"")],
        "issuer": [response(resource_metadata)],
        "registration": [response(resource_metadata), response(server_metadata)],
    }
    responses = prefixes[stage] + [OAuthHttpResponse(
        status=status, body=b'{"error":"sensitive-provider-error","endpoint":"https://secret.example"}',
    )]
    transport = InMemoryOAuthHttpTransport(responses=responses)
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await provider.prepare(preparation)
    assert str(caught.value) == "Personal OAuth provider request failed"
    assert len(transport.requests) == len(responses)
    assert not transport.responses


@pytest.mark.asyncio
async def test_resource_root_fallback_on_not_found(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object],
    server_metadata: dict[str, object], client_metadata: dict[str, object],
) -> None:
    transport = InMemoryOAuthHttpTransport(responses=[
        OAuthHttpResponse(status=404, body=b""), response(resource_metadata), response(server_metadata), response(client_metadata),
    ])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    await provider.prepare(preparation)
    assert transport.requests[1].url == "https://resource.example/.well-known/oauth-protected-resource"


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "value"), [
    ("issuer", "https://issuer.example/other"),
    ("code_challenge_methods_supported", ["plain"]),
    ("code_challenge_methods_supported", []),
    ("grant_types_supported", ["client_credentials"]),
    ("response_types_supported", ["token"]),
    ("token_endpoint_auth_methods_supported", ["client_secret_basic"]),
    ("authorization_response_iss_parameter_supported", None),
    ("authorization_response_iss_parameter_supported", "true"),
    ("authorization_endpoint", "https://issuer.example/auth?scope=extra"),
    ("token_endpoint", "http://issuer.example/token"),
    ("registration_endpoint", "https://user:password@issuer.example/register"),
])
async def test_unsupported_server_metadata_fails_before_registration(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object], server_metadata: dict[str, object],
    field: str, value: object,
) -> None:
    server_metadata[field] = value
    transport = InMemoryOAuthHttpTransport(responses=[response(resource_metadata), response(server_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)
    assert len(transport.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "value"), [
    ("client_secret", "provider-secret"), ("scope", "read"), ("scope", " "),
    ("redirect_uris", ["https://attacker.example/callback"]),
    ("redirect_uris", []), ("client_id", ""),
    ("token_endpoint_auth_method", "client_secret_post"),
    ("grant_types", ["authorization_code", "refresh_token"]), ("response_types", ["token"]),
])
async def test_registration_requires_exact_public_client_subset(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object], server_metadata: dict[str, object],
    client_metadata: dict[str, object], field: str, value: object,
) -> None:
    client_metadata[field] = value
    transport: OAuthHttpTransport = InMemoryOAuthHttpTransport(responses=[response(resource_metadata), response(server_metadata), response(client_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await provider.prepare(preparation)
    assert str(caught.value) == "Personal OAuth provider is unsupported"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["issuer", "endpoint_url", "redirect_uri", "code_verifier", "state", "authorization_url"])
async def test_exchange_bindings_fail_before_network(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object], server_metadata: dict[str, object],
    client_metadata: dict[str, object], field: str,
) -> None:
    transport = InMemoryOAuthHttpTransport(responses=[response(resource_metadata), response(server_metadata), response(client_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    prepared = await provider.prepare(preparation)
    command = exchange_command(preparation, prepared)
    if field == "issuer":
        command = command.model_copy(update={"issuer": PresentCallbackIssuer(kind="present", value="https://wrong.example")})
    elif field == "authorization_url":
        changed = prepared.model_copy(update={"authorization_url": SecretStr("https://wrong.example")})
        command = command.model_copy(update={"attempt": command.attempt.model_copy(update={"prepared": changed})})
    else:
        changed_value = "https://wrong.example" if field in ("endpoint_url", "redirect_uri") else SecretStr("b" * 43)
        changed_preparation = preparation.model_copy(update={field: changed_value})
        command = command.model_copy(update={"attempt": command.attempt.model_copy(update={"preparation": changed_preparation})})
    with pytest.raises(PersonalOAuthProviderFailure):
        await provider.exchange(command)
    assert len(transport.requests) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "value"), [
    ("scope", "read"), ("scope", " "), ("scope", None), ("token_type", "Basic"),
    ("access_token", ""), ("access_token", "token\nsecret"), ("access_token", "masked token"),
    ("expires_in", -1), ("expires_in", True), ("expires_in", "3600"), ("expires_in", 10**100),
    ("refresh_token", ""), ("refresh_token", "secret\nunsafe"), ("error", "provider-sensitive-message"),
])
async def test_invalid_token_response_fails_once_without_leaking_provider_messages(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object], server_metadata: dict[str, object],
    client_metadata: dict[str, object], field: str, value: object,
) -> None:
    token: dict[str, object] = {"access_token": "valid-token", "token_type": "Bearer"}
    token[field] = value
    transport = InMemoryOAuthHttpTransport(responses=[response(resource_metadata), response(server_metadata), response(client_metadata), response(token)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    prepared = await provider.prepare(preparation)
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await provider.exchange(exchange_command(preparation, prepared))
    assert str(caught.value) == "Personal OAuth provider request failed"
    assert len(transport.requests) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    b'{"resource":"one","resource":"two","authorization_servers":[]}',
    b"[]", b"not json", b" " * 1_048_577,
])
async def test_invalid_resource_json_is_rejected(preparation: PreparePersonalOAuth, body: bytes) -> None:
    transport: OAuthHttpTransport = InMemoryOAuthHttpTransport(responses=[OAuthHttpResponse(status=200, body=body)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["https://resource.example/other", "https://resource.example/mcp/"])
async def test_resource_identity_is_exact(preparation: PreparePersonalOAuth, resource_metadata: dict[str, object], resource: str) -> None:
    resource_metadata["resource"] = resource
    transport = InMemoryOAuthHttpTransport(responses=[response(resource_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)
    assert len(transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://resource.example/mcp", "https://user:secret@resource.example/mcp", "https://resource.example/mcp#fragment",
    "https://resource.example/mcp?query", "https://resource.example/mcp?", "https://resource.example/mcp#",
    "https://resource.example/\nmcp", "https://resource.example/%0dmcp", "https://resource.example:0/mcp",
    "https://resource.example\\@other.example/mcp", "https://resource.example%2fother/mcp",
])
async def test_unsafe_endpoint_urls_fail_before_network(preparation: PreparePersonalOAuth, url: str) -> None:
    transport = InMemoryOAuthHttpTransport(responses=[])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation.model_copy(update={"endpoint_url": url}))
    assert not transport.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("verifier", ["short", "a" * 129, "!" * 43, "é" * 43])
async def test_invalid_pkce_is_rejected_before_network(preparation: PreparePersonalOAuth, verifier: str) -> None:
    transport = InMemoryOAuthHttpTransport(responses=[])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport=transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation.model_copy(update={"code_verifier": SecretStr(verifier)}))
    assert not transport.requests

