import hashlib
import json

import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.setup import DiscoveredPersonalOAuthSetupProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthPolicy, PreconfiguredConfidentialOAuthClient, PreconfiguredPublicOAuthClient
from umbod.core.connectors.downstream_mcp.personal_oauth_setup.models import DiscoverPersonalOAuthSetup, PersonalOAuthSetupScopeMismatch, ValidatePersonalOAuthSetup, ValidatedPersonalOAuthSetup
from umbod.core.connectors.downstream_mcp.personal_oauth_setup.ports import PersonalOAuthSetupProvider
from umbod.core.invocation.diagnostics import DownstreamHttpResponse

from .conftest import ProviderCase, response


def discovery_command(case: ProviderCase) -> DiscoverPersonalOAuthSetup:
    return DiscoverPersonalOAuthSetup(
        endpoint_url=case.preparation.endpoint_url,
        redirect_uri=case.preparation.redirect_uri,
        policy=case.preparation.policy,
    )


def validation_command(case: ProviderCase) -> ValidatePersonalOAuthSetup:
    return ValidatePersonalOAuthSetup(**discovery_command(case).model_dump())


def setup_provider(transport: InMemoryOAuthHttpTransport) -> PersonalOAuthSetupProvider:
    return DiscoveredPersonalOAuthSetupProvider(CallbackURLPolicy.STRICT, transport)


@pytest.mark.asyncio
async def test_discovery_only_reads_metadata_and_leaves_advertised_permissions_unapproved(provider_case: ProviderCase) -> None:
    provider_case.resource_metadata["scopes_supported"] = ["documents.read"]
    provider_case.server_metadata["scopes_supported"] = ["documents.write", "documents.read"]
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    command = discovery_command(provider_case)
    result = await setup_provider(transport).discover(command)
    assert result.available_scopes == ("documents.read", "documents.write")
    assert command.policy.requested_scopes == ()
    assert [request.method for request in transport.requests] == ["GET", "GET"]
    assert {destination.url for destination in transport.destinations} == {
        "https://issuer.example/authorize", "https://issuer.example/token", "https://issuer.example/register",
    }
    assert "public-client" not in result.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["documents.read", "tasks:read"])
async def test_provider_defaults_are_reported_as_scope_mismatch_without_login_or_approval(provider_case: ProviderCase, scope: str) -> None:
    provider_case.client_metadata["scope"] = scope
    provider_case.client_metadata["registration_access_token"] = "secret-registration-token"
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
        OAuthHttpResponse(status=201, body=json.dumps(provider_case.client_metadata).encode()),
    ])
    command = validation_command(provider_case)
    result = await setup_provider(transport).validate(command)
    assert isinstance(result, PersonalOAuthSetupScopeMismatch)
    assert result.returned_scopes == (scope,)
    assert result.downstream_response == DownstreamHttpResponse(status_code=201)
    assert command.policy.requested_scopes == ()
    assert [request.method for request in transport.requests] == ["GET", "GET", "POST"]
    registration = json.loads(transport.requests[-1].body.get_secret_value())
    assert "scope" not in registration
    assert "state" not in registration
    assert "code_challenge" not in registration
    assert "secret-registration-token" not in result.model_dump_json()
    assert "public-client" not in result.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("advertisement", [None, [], ["another.scope"]])
async def test_manually_approved_scopes_do_not_require_matching_advertisements(provider_case: ProviderCase, advertisement: list[str] | None) -> None:
    if advertisement is not None:
        provider_case.server_metadata["scopes_supported"] = advertisement
    provider_case.client_metadata["scope"] = "write read"
    command = validation_command(provider_case)
    command = command.model_copy(update={"policy": PersonalOAuthPolicy(
        revision="approved", requested_scopes=("read", "write"), client=command.policy.client,
    )})
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata), response(provider_case.client_metadata),
    ])
    result = await setup_provider(transport).validate(command)
    assert isinstance(result, ValidatedPersonalOAuthSetup)
    assert result.returned_scopes == ("read", "write")
    assert json.loads(transport.requests[-1].body.get_secret_value())["scope"] == "read write"


@pytest.mark.asyncio
@pytest.mark.parametrize("echo_scope", [False, True])
async def test_absent_or_explicit_empty_registration_scope_remains_compatible(provider_case: ProviderCase, echo_scope: bool) -> None:
    if echo_scope:
        provider_case.client_metadata["scope"] = ""
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata), response(provider_case.client_metadata),
    ])
    result = await setup_provider(transport).validate(validation_command(provider_case))
    assert isinstance(result, ValidatedPersonalOAuthSetup)
    assert result.returned_scopes == ()
    assert result.scope_source == ("registration" if echo_scope else "not_returned")
    assert len(transport.requests) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("confidential", [False, True])
async def test_preconfigured_clients_only_validate_metadata_and_never_send_credentials(provider_case: ProviderCase, confidential: bool) -> None:
    client = PreconfiguredConfidentialOAuthClient(
        issuer_url="https://issuer.example/tenant", client_id="private-client-sentinel",
        token_endpoint_auth_method="client_secret_basic", client_secret=SecretStr("private-secret-sentinel"),
    ) if confidential else PreconfiguredPublicOAuthClient(issuer_url="https://issuer.example/tenant", client_id="private-client-sentinel")
    provider_case.server_metadata.pop("registration_endpoint")
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = ["none", "client_secret_basic"]
    command = validation_command(provider_case)
    command = command.model_copy(update={"policy": PersonalOAuthPolicy(revision="static", requested_scopes=(), client=client)})
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    result = await setup_provider(transport).validate(command)
    assert isinstance(result, ValidatedPersonalOAuthSetup)
    assert result.discovery.registration_mode == client.kind
    assert result.scope_source == "not_checked"
    assert [request.method for request in transport.requests] == ["GET", "GET"]
    assert "private-client-sentinel" not in result.model_dump_json()
    assert "private-secret-sentinel" not in result.model_dump_json()
    assert all(request.authentication.kind == "none" for request in transport.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer_advertisement", ["omitted", "false"])
async def test_setup_uses_the_same_issuer_bound_callback_as_user_authorization(provider_case: ProviderCase, issuer_advertisement: str) -> None:
    if issuer_advertisement == "omitted":
        provider_case.server_metadata.pop("authorization_response_iss_parameter_supported")
    else:
        provider_case.server_metadata["authorization_response_iss_parameter_supported"] = False
    callback = provider_case.preparation.redirect_uri + "/issuer/" + hashlib.sha256(b"https://issuer.example/tenant").hexdigest()
    provider_case.client_metadata["redirect_uris"] = [callback]
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata), response(provider_case.client_metadata),
    ])
    result = await setup_provider(transport).validate(validation_command(provider_case))
    assert isinstance(result, ValidatedPersonalOAuthSetup)
    assert result.discovery.redirect_uri == callback
    assert json.loads(transport.requests[-1].body.get_secret_value())["redirect_uris"] == [callback]
    assert [request.method for request in transport.requests] == ["GET", "GET", "POST"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["authorization_endpoint", "token_endpoint", "registration_endpoint"])
async def test_unsafe_discovered_destinations_fail_before_registration(provider_case: ProviderCase, field: str) -> None:
    provider_case.server_metadata[field] = "https://127.0.0.1/private"
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await setup_provider(transport).validate(validation_command(provider_case))
    assert [request.method for request in transport.requests] == ["GET", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value,reason", [
    ("issuer", "https://another.example", "issuer_mismatch"),
    ("code_challenge_methods_supported", ["plain"], "pkce_s256_required"),
    ("grant_types_supported", ["client_credentials"], "authorization_code_required"),
    ("response_types_supported", ["token"], "code_response_required"),
    ("token_endpoint_auth_methods_supported", ["client_secret_basic"], "client_auth_required"),
    ("registration_endpoint", "", "registration_unavailable"),
])
async def test_known_metadata_incompatibilities_provide_actionable_safe_reasons(provider_case: ProviderCase, field: str, value: object, reason: str) -> None:
    provider_case.server_metadata[field] = value
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await setup_provider(transport).validate(validation_command(provider_case))
    assert caught.value.evidence.reason == reason
    assert len(transport.requests) == 2


@pytest.mark.asyncio
async def test_discovery_suggests_a_unique_issuer_without_silently_changing_static_configuration(provider_case: ProviderCase) -> None:
    command = validation_command(provider_case)
    command = command.model_copy(update={"policy": PersonalOAuthPolicy(
        revision="static", requested_scopes=(), client=PreconfiguredPublicOAuthClient(
            issuer_url="https://incorrect.example", client_id="existing-client",
        ),
    )})
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    discovered = await setup_provider(transport).discover(command)
    assert discovered.issuer_url == "https://issuer.example/tenant"
    assert command.policy.client.issuer_url == "https://incorrect.example"
    assert [request.method for request in transport.requests] == ["GET", "GET"]
    validation_transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await setup_provider(validation_transport).validate(command)
    assert caught.value.evidence.reason == "issuer_mismatch"
    assert len(validation_transport.requests) == 1


@pytest.mark.asyncio
async def test_ambiguous_issuer_is_not_silently_selected(provider_case: ProviderCase) -> None:
    provider_case.resource_metadata["authorization_servers"] = ["https://issuer.example/tenant", "https://other.example"]
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await setup_provider(transport).validate(validation_command(provider_case))
    assert len(transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("scopes", [["bad scope"], ["same", "same"], ["x" * 257], [f"scope{index}" for index in range(65)]])
async def test_invalid_scope_advertisements_do_not_become_configuration(provider_case: ProviderCase, scopes: list[str]) -> None:
    provider_case.server_metadata["scopes_supported"] = scopes
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await setup_provider(transport).discover(discovery_command(provider_case))
    assert len(transport.requests) == 2


@pytest.mark.asyncio
async def test_registration_contract_failure_preserves_success_status_without_secret_payload(provider_case: ProviderCase) -> None:
    provider_case.client_metadata["client_secret"] = "secret-sentinel"
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
        OAuthHttpResponse(status=201, body=json.dumps(provider_case.client_metadata).encode()),
    ])
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await setup_provider(transport).validate(validation_command(provider_case))
    assert caught.value.evidence.stage == "registration"
    assert caught.value.evidence.downstream_response == DownstreamHttpResponse(status_code=201)
    assert "secret-sentinel" not in str(caught.value)
    assert "secret-sentinel" not in caught.value.evidence.model_dump_json()
    assert len(transport.requests) == 3


@pytest.mark.asyncio
async def test_rejected_registration_is_not_retried_or_returned_raw(provider_case: ProviderCase) -> None:
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
        OAuthHttpResponse(status=400, body=b'{"error_description":"secret-sentinel"}'),
    ])
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await setup_provider(transport).validate(validation_command(provider_case))
    assert caught.value.evidence.stage == "registration"
    assert caught.value.evidence.reason == "provider_rejected"
    assert caught.value.evidence.downstream_response == DownstreamHttpResponse(status_code=400)
    assert "secret-sentinel" not in str(caught.value)
    assert len(transport.requests) == 3
