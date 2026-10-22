import json
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import CallbackIssuer, GenericRoute, IssuerBinding, IssuerRoute, MissingCallbackIssuer, PresentCallbackIssuer, issuer_callback_uri, issuer_route_key
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure, PreparedPersonalOAuth
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthProvider

from .conftest import ProviderCase, exchange_command, response


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ("omitted", "false", "true"))
async def test_discovered_capability_binds_registration_authorization_and_exchange(
    provider_case: ProviderCase, flag: str,
) -> None:
    preparation = provider_case.preparation
    resource_metadata = provider_case.resource_metadata
    server_metadata = provider_case.server_metadata
    client_metadata = provider_case.client_metadata
    server_metadata.pop("authorization_response_iss_parameter_supported")
    if flag != "omitted":
        server_metadata["authorization_response_iss_parameter_supported"] = flag == "true"
    issuer = str(server_metadata["issuer"])
    redirect = preparation.redirect_uri if flag == "true" else issuer_callback_uri(preparation.redirect_uri, issuer)
    client_metadata["redirect_uris"] = [redirect]
    transport = InMemoryOAuthHttpTransport([
        response(resource_metadata), response(server_metadata), response(client_metadata),
        response({"access_token": "access", "token_type": "Bearer"}),
    ])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport)
    prepared = await provider.prepare(preparation)
    assert prepared.callback_binding.kind == ("generic" if flag == "true" else "issuer")
    assert preparation.redirect_uri != redirect or flag == "true"
    assert json.loads(transport.requests[2].body.get_secret_value())["redirect_uris"] == [redirect]
    assert parse_qs(urlsplit(prepared.authorization_url.get_secret_value()).query)["redirect_uri"] == [redirect]
    command = exchange_command(preparation, prepared).model_copy(update={"issuer": MissingCallbackIssuer(kind="missing")})
    if flag == "true":
        with pytest.raises(PersonalOAuthProviderFailure):
            await provider.exchange(command)
        assert len(transport.requests) == 3
        return
    authorization = await provider.exchange(command)
    assert parse_qs(transport.requests[-1].body.get_secret_value())["redirect_uri"] == [redirect]
    assert json.loads(authorization.authorization.get_secret_value())["redirect_uri"] == redirect


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ("issuer", "hash", "redirect", "context", "route", "generic", "empty", "mismatch"))
async def test_tampered_bound_exchange_is_rejected_before_token_post(
    provider_case: ProviderCase, tamper: str,
) -> None:
    preparation = provider_case.preparation
    resource_metadata = provider_case.resource_metadata
    server_metadata = provider_case.server_metadata
    client_metadata = provider_case.client_metadata
    server_metadata["authorization_response_iss_parameter_supported"] = False
    issuer = str(server_metadata["issuer"])
    client_metadata["redirect_uris"] = [issuer_callback_uri(preparation.redirect_uri, issuer)]
    transport = InMemoryOAuthHttpTransport([response(resource_metadata), response(server_metadata), response(client_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport)
    prepared = await provider.prepare(preparation)
    binding = prepared.callback_binding
    assert isinstance(binding, IssuerBinding)
    route = IssuerRoute(kind="issuer", issuer_key=binding.issuer_key)
    response_issuer: CallbackIssuer = MissingCallbackIssuer(kind="missing")
    if tamper in ("issuer", "hash", "redirect"):
        field, value = {
            "issuer": ("expected_issuer", issuer + "/"), "hash": ("issuer_key", "0" * 64),
            "redirect": ("redirect_uri", preparation.redirect_uri),
        }[tamper]
        prepared = prepared.model_copy(update={"callback_binding": binding.model_copy(update={field: value})})
    elif tamper == "context":
        context = json.loads(prepared.context.get_secret_value())
        context["issuer"] = issuer + "/"
        prepared = prepared.model_copy(update={"context": SecretStr(json.dumps(context))})
    elif tamper == "route":
        route = IssuerRoute(kind="issuer", issuer_key="0" * 64)
    elif tamper in ("empty", "mismatch"):
        response_issuer = PresentCallbackIssuer.model_construct(kind="present", value="" if tamper == "empty" else issuer + "/")
    command = exchange_command(preparation, prepared).model_copy(update={
        "route": GenericRoute(kind="generic") if tamper == "generic" else route,
        "issuer": response_issuer,
    })
    with pytest.raises(PersonalOAuthProviderFailure):
        await provider.exchange(command)
    assert len(transport.requests) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer", (
    MissingCallbackIssuer(kind="missing"), PresentCallbackIssuer.model_construct(kind="present", value=""),
    PresentCallbackIssuer(kind="present", value="https://issuer.example/tenant/"),
))
async def test_legacy_generic_exchange_still_requires_exact_actual_issuer(
    provider_case: ProviderCase, issuer: CallbackIssuer,
) -> None:
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata), response(provider_case.client_metadata),
    ])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport)
    prepared = await provider.prepare(provider_case.preparation)
    legacy = PreparedPersonalOAuth.model_validate_json(json.dumps({
        "authorization_url": prepared.authorization_url.get_secret_value(),
        "context": prepared.context.get_secret_value(),
    }))
    command = exchange_command(provider_case.preparation, legacy).model_copy(update={"issuer": issuer})
    with pytest.raises(PersonalOAuthProviderFailure):
        await provider.exchange(command)
    assert len(transport.requests) == 3


def test_exact_issuer_slash_changes_route_hash() -> None:
    assert issuer_route_key("https://issuer.example") != issuer_route_key("https://issuer.example/")


def test_old_prepared_json_decodes_as_legacy_generic_without_promotion() -> None:
    prepared = PreparedPersonalOAuth.model_validate_json(json.dumps({
        "authorization_url": "https://issuer.example/authorize", "context": "opaque",
    }))
    assert prepared.callback_binding.kind == "legacy_generic"
