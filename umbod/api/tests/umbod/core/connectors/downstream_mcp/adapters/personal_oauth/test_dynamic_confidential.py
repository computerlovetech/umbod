import json
from datetime import datetime, timedelta
from urllib.parse import parse_qs

import pytest
from pydantic import SecretStr

from tests.support.personal_oauth_applications import InMemoryPersonalOAuthApplicationStore, application_clock
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.refresh import StoredPersonalOAuthRefreshProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.setup import DiscoveredPersonalOAuthSetupProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpResponse, OAuthHttpRequest
from umbod.core.connectors.downstream_mcp.personal.oauth.grants.models import PersonalOAuthGrant
from umbod.core.connectors.downstream_mcp.personal.oauth.authorization.models import PreparePersonalOAuth, PersonalOAuthProviderUnsupported, PersonalOAuthProviderFailure
from umbod.core.connectors.downstream_mcp.personal.oauth.refresh.provider_models import RefreshPersonalOAuth, PersonalOAuthRefreshUncertain
from umbod.core.connectors.downstream_mcp.personal.oauth.configuration import DynamicConfidentialOAuthClient, PersonalOAuthPolicy
from umbod.core.connectors.downstream_mcp.personal.oauth.setup.models import ValidatePersonalOAuthSetup

from .conftest import ProviderCase, exchange_command, response


def confidential_preparation(case: ProviderCase, method: str) -> PreparePersonalOAuth:
    return PreparePersonalOAuth(
        **case.preparation.model_dump(exclude={"policy", "connector_id"}),
        connector_id="connector",
        policy=PersonalOAuthPolicy(revision="configured", requested_scopes=(), client=DynamicConfidentialOAuthClient(
            token_endpoint_auth_method=method, approved_issuers=("https://issuer.example/tenant",),
        )),
    )


def registration_response(case: ProviderCase, method: str, changes: dict[str, object]) -> OAuthHttpResponse:
    return OAuthHttpResponse(status=201, body=json.dumps({
        **case.client_metadata, "client_id": "registered-client", "token_endpoint_auth_method": method,
        "client_secret": "registered-secret-sentinel", "client_secret_expires_at": 0, **changes,
    }).encode())


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["client_secret_basic", "client_secret_post"])
async def test_registration_reused_across_users_and_restart_safe_exchange_refresh(provider_case: ProviderCase, method: str) -> None:
    preparation = confidential_preparation(provider_case, method)
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = [method]
    provider_case.server_metadata["grant_types_supported"] = ["authorization_code", "refresh_token"]
    applications = InMemoryPersonalOAuthApplicationStore(application_clock)
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata), registration_response(provider_case, method, {}),
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
    ])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, applications, application_clock)
    first = await provider.prepare(preparation)
    second = await provider.prepare(preparation.model_copy(update={"state": SecretStr("second-user-state")}))
    assert len([request for request in transport.requests if request.method == "POST"]) == 1
    assert json.loads(first.context.get_secret_value())["application_reference"] == json.loads(second.context.get_secret_value())["application_reference"]
    assert "registered-secret-sentinel" not in first.context.get_secret_value()
    token_transport = InMemoryOAuthHttpTransport([response({
        "access_token": access, "refresh_token": "user-refresh", "token_type": "Bearer", "expires_in": 60,
    }) for access in ("user-access", "second-user-access")])
    resumed = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, token_transport, applications, application_clock)
    grant = PersonalOAuthGrant.model_validate_json((await resumed.exchange(exchange_command(preparation, first))).authorization.get_secret_value())
    second_preparation = preparation.model_copy(update={"state": SecretStr("second-user-state")})
    second_command = exchange_command(second_preparation, second)
    second_key = second_command.attempt.query.key.model_copy(update={"principal": second_command.attempt.query.key.principal.model_copy(update={"subject": "second-owner"})})
    second_command = second_command.model_copy(update={"attempt": second_command.attempt.model_copy(update={
        "query": second_command.attempt.query.model_copy(update={"key": second_key}),
    })})
    second_grant = PersonalOAuthGrant.model_validate_json((await resumed.exchange(second_command)).authorization.get_secret_value())
    assert grant.key != second_grant.key
    assert grant.application_reference == second_grant.application_reference
    assert grant.application_reference.kind == "registered"
    assert "registered-secret-sentinel" not in grant.model_dump_json()
    request = token_transport.requests[0]
    parameters = parse_qs(request.body.get_secret_value())
    assert request.authentication.kind == ("basic" if method == "client_secret_basic" else "none")
    if method == "client_secret_post":
        assert parameters["client_secret"] == ["registered-secret-sentinel"]
        assert parameters["client_id"] == ["registered-client"]
    else:
        assert request.authentication.client_id.get_secret_value() == "registered-client"
        assert request.authentication.client_secret.get_secret_value() == "registered-secret-sentinel"
        assert "client_secret" not in parameters
    refresh_transport = InMemoryOAuthHttpTransport([response({"access_token": "renewed-access", "token_type": "Bearer", "expires_in": 60})])
    refresher = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, refresh_transport, applications, application_clock)
    renewed = await refresher.refresh(RefreshPersonalOAuth(policy=preparation.policy, grant=grant, now=application_clock(), timeout_seconds=20))
    assert PersonalOAuthGrant.model_validate_json(renewed.authorization.get_secret_value()).application_reference == grant.application_reference
    assert refresh_transport.requests[0].authentication.kind == request.authentication.kind


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"client_secret": ""}, {"client_secret": "   "}, {"client_secret": "bad\nsecret"},
    {"client_secret_expires_at": -1}, {"client_secret_expires_at": True},
    {"token_endpoint_auth_method": "none"}, {"scope": "unapproved"},
    {"redirect_uris": ["https://other.example/callback"]},
])
async def test_invalid_registration_is_fenced_without_automatic_replay(provider_case: ProviderCase, changes: dict[str, object]) -> None:
    method = "client_secret_basic"
    preparation = confidential_preparation(provider_case, method)
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = [method]
    applications = InMemoryPersonalOAuthApplicationStore(application_clock)
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata), registration_response(provider_case, method, changes),
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
    ])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, applications, application_clock)
    for _ in range(2):
        with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
            await provider.prepare(preparation)
        assert caught.value.evidence.stage == "registration"
    assert len([request for request in transport.requests if request.method == "POST"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["client_secret_basic", "client_secret_post"])
async def test_confidential_scope_mismatch_retains_registration_response_evidence(provider_case: ProviderCase, method: str) -> None:
    preparation = confidential_preparation(provider_case, method)
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = [method]
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
        registration_response(provider_case, method, {"scope": "private-unapproved-scope"}),
    ])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, InMemoryPersonalOAuthApplicationStore(application_clock), application_clock)
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await provider.prepare(preparation)
    assert caught.value.evidence.stage == "registration"
    assert caught.value.evidence.reason == "scope_mismatch"
    assert caught.value.evidence.downstream_response.status_code == 201
    evidence = caught.value.evidence.model_dump_json()
    assert "private-unapproved-scope" not in evidence
    assert "registered-secret-sentinel" not in evidence


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["client_secret_basic", "client_secret_post"])
@pytest.mark.parametrize("expiry_present", [False, True])
async def test_confidential_registration_requires_explicit_secret_expiry_before_consent(provider_case: ProviderCase, method: str, expiry_present: bool) -> None:
    preparation = confidential_preparation(provider_case, method)
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = [method]
    provider_case.server_metadata["grant_types_supported"] = ["authorization_code", "refresh_token"]
    registration = {
        "client_name": "Umbod", "application_type": "web",
        "redirect_uris": [preparation.redirect_uri], "token_endpoint_auth_method": method,
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "client_id": "kind-personal-client-sentinel", "client_secret": "kind-personal-dcr-secret-sentinel",
    }
    if expiry_present:
        registration["client_secret_expires_at"] = 0
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
        OAuthHttpResponse(status=201, body=json.dumps(registration).encode()),
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
    ])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, InMemoryPersonalOAuthApplicationStore(application_clock), application_clock)
    if expiry_present:
        prepared = await provider.prepare(preparation)
        assert parse_qs(prepared.authorization_url.get_secret_value().split("?", 1)[1])["client_id"] == ["kind-personal-client-sentinel"]
        assert "kind-personal-dcr-secret-sentinel" not in prepared.context.get_secret_value()
        return
    with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
        await provider.prepare(preparation)
    assert caught.value.evidence.stage == "registration"
    assert caught.value.evidence.reason == "invalid_response"
    assert caught.value.evidence.downstream_response.status_code == 201
    assert "kind-personal-dcr-secret-sentinel" not in caught.value.evidence.model_dump_json()
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)
    assert [request.method for request in transport.requests] == ["GET", "GET", "POST", "GET", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 500])
async def test_registration_denial_is_not_replayed(provider_case: ProviderCase, status: int) -> None:
    preparation = confidential_preparation(provider_case, "client_secret_basic")
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = ["client_secret_basic"]
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata), OAuthHttpResponse(status=status, body=b'{"error":"secret-sentinel"}'),
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
    ])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, InMemoryPersonalOAuthApplicationStore(application_clock), application_clock)
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await provider.prepare(preparation)
    assert caught.value.evidence.stage == "registration"
    assert "secret-sentinel" not in caught.value.evidence.model_dump_json()
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)
    assert len([request for request in transport.requests if request.method == "POST"]) == 1


@pytest.mark.asyncio
async def test_expired_registration_fails_exchange_and_refresh_before_http(provider_case: ProviderCase) -> None:
    now = application_clock()
    def clock() -> datetime:
        return now
    preparation = confidential_preparation(provider_case, "client_secret_basic")
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = ["client_secret_basic"]
    applications = InMemoryPersonalOAuthApplicationStore(clock)
    transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
        registration_response(provider_case, "client_secret_basic", {"client_secret_expires_at": int((now + timedelta(minutes=1)).timestamp())}),
    ])
    prepared = await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, applications, clock).prepare(preparation)
    now += timedelta(minutes=2)
    empty = InMemoryOAuthHttpTransport([])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, empty, applications, clock)
    with pytest.raises(PersonalOAuthProviderFailure):
        await provider.exchange(exchange_command(preparation, prepared))
    assert empty.requests == []
    now -= timedelta(minutes=2)
    token_transport = InMemoryOAuthHttpTransport([response({
        "access_token": "user-access", "refresh_token": "user-refresh", "token_type": "Bearer", "expires_in": 60,
    })])
    authorized = await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, token_transport, applications, clock).exchange(exchange_command(preparation, prepared))
    grant = PersonalOAuthGrant.model_validate_json(authorized.authorization.get_secret_value())
    now += timedelta(minutes=2)
    with pytest.raises(PersonalOAuthRefreshUncertain):
        await StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, empty, applications, clock).refresh(
            RefreshPersonalOAuth(policy=preparation.policy, grant=grant, now=now, timeout_seconds=20),
        )
    assert empty.requests == []


class RegistrationTimeoutTransport(InMemoryOAuthHttpTransport):
    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        if command.method == "POST":
            self.requests.append(command)
            raise TimeoutError("private-timeout-sentinel")
        return await super().request(command)


@pytest.mark.asyncio
async def test_registration_timeout_remains_fenced_and_preserves_sanitized_evidence(provider_case: ProviderCase) -> None:
    preparation = confidential_preparation(provider_case, "client_secret_basic")
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = ["client_secret_basic"]
    transport = RegistrationTimeoutTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
        response(provider_case.resource_metadata), response(provider_case.server_metadata),
    ])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, InMemoryPersonalOAuthApplicationStore(application_clock), application_clock)
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await provider.prepare(preparation)
    assert caught.value.evidence.stage == "registration"
    assert caught.value.evidence.reason == "timeout"
    assert "private-timeout-sentinel" not in caught.value.evidence.model_dump_json()
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)
    assert len([request for request in transport.requests if request.method == "POST"]) == 1


@pytest.mark.asyncio
async def test_confidential_setup_is_metadata_only(provider_case: ProviderCase) -> None:
    preparation = confidential_preparation(provider_case, "client_secret_basic")
    provider_case.server_metadata["token_endpoint_auth_methods_supported"] = ["client_secret_basic"]
    transport = InMemoryOAuthHttpTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    result = await DiscoveredPersonalOAuthSetupProvider(CallbackURLPolicy.STRICT, transport).validate(ValidatePersonalOAuthSetup(
        endpoint_url=preparation.endpoint_url, redirect_uri=preparation.redirect_uri, policy=preparation.policy,
    ))
    assert result.scope_source == "not_checked"
    assert result.discovery.registration_mode == "dynamic_confidential"
    assert [request.method for request in transport.requests] == ["GET", "GET"]


def test_dynamic_confidential_requires_connector_identifier(provider_case: ProviderCase) -> None:
    preparation = confidential_preparation(provider_case, "client_secret_basic")
    with pytest.raises(ValueError):
        PreparePersonalOAuth.model_validate({**preparation.model_dump(), "connector_id": ""})
