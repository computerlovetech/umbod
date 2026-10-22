import json
import logging
import ssl
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import anyio
import httpcore
import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import issuer_callback_uri
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.network import PublicAddressNetworkBackend, SafeOAuthHttpTransport
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.refresh import StoredPersonalOAuthRefreshProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import (
    BasicOAuthHttpAuthentication,
    InMemoryOAuthHttpTransport,
    OAuthHttpRequest,
    OAuthHttpResponse,
)
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import (
    AbsentPersonalRefreshToken,
    ExpiringPersonalToken,
    PersonalOAuthGrant,
    PresentPersonalRefreshToken,
    UnknownPersonalTokenLifetime,
)
from umbod.core.connectors.downstream_mcp.personal_connections.models import CanonicalPrincipal, PersonalConnectionKey
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_provider_models import (
    PersonalOAuthRefreshDenied,
    PersonalOAuthRefreshUncertain,
    RefreshPersonalOAuth,
)
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_provider_ports import PersonalOAuthRefreshProvider
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration.models import (
    PersonalOAuthPolicy,
    PreconfiguredConfidentialOAuthClient,
    PreconfiguredPublicOAuthClient,
)

from .test_network import MemoryNetwork, MemoryStream


@pytest.fixture
def refresh_command() -> RefreshPersonalOAuth:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    policy = PersonalOAuthPolicy(
        revision="configuration", requested_scopes=("read", "write"),
        client=PreconfiguredPublicOAuthClient(issuer_url="https://issuer.example", client_id="client"),
    )
    return RefreshPersonalOAuth(
        policy=policy, now=now, timeout_seconds=20,
        grant=PersonalOAuthGrant(
            version=2, key=PersonalConnectionKey(
                principal=CanonicalPrincipal(namespace="namespace", subject="owner"), connector_id="connector",
            ), issuer="https://issuer.example", resource="https://resource.example/mcp",
            client_id="client", token_endpoint="https://tokens.example/token",
            redirect_uri="https://umbod.example/callback", client_mode="preconfigured_public",
            token_endpoint_auth_method="none", requested_scopes=policy.requested_scopes,
            granted_scopes=("read",), configuration_revision=policy.revision,
            issued_at=now - timedelta(hours=2), lifetime=ExpiringPersonalToken(expires_at=now - timedelta(hours=1)),
            access_token=SecretStr("old-access"), refresh_token=PresentPersonalRefreshToken(token=SecretStr("old-refresh")),
        ),
    )


def success_response(**changes: object) -> OAuthHttpResponse:
    return OAuthHttpResponse(status=200, body=json.dumps({
        "access_token": "new-access", "token_type": "Bearer", "expires_in": 3600, **changes,
    }).encode())


@pytest.mark.asyncio
async def test_refresh_preserves_issuer_bound_redirect_uri(refresh_command: RefreshPersonalOAuth) -> None:
    redirect_uri = issuer_callback_uri(refresh_command.grant.redirect_uri, refresh_command.grant.issuer)
    command = refresh_command.model_copy(update={
        "grant": refresh_command.grant.model_copy(update={"redirect_uri": redirect_uri}),
    })
    transport = InMemoryOAuthHttpTransport([success_response()])
    provider: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)
    authorization = await provider.refresh(command)
    renewed = PersonalOAuthGrant.model_validate_json(authorization.authorization.get_secret_value())
    assert renewed.redirect_uri == redirect_uri
    assert len(transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["none", "client_secret_basic", "client_secret_post"])
async def test_refresh_posts_only_bound_refresh_parameters(refresh_command: RefreshPersonalOAuth, method: str) -> None:
    command = refresh_command
    if method != "none":
        client = PreconfiguredConfidentialOAuthClient.model_validate({
            "kind": "preconfigured_confidential", "issuer_url": command.grant.issuer,
            "client_id": command.grant.client_id, "token_endpoint_auth_method": method,
            "client_secret": SecretStr("client-secret"),
        })
        command = command.model_copy(update={
            "policy": command.policy.model_copy(update={"client": client}),
            "grant": command.grant.model_copy(update={"client_mode": client.kind, "token_endpoint_auth_method": method}),
        })
    transport = InMemoryOAuthHttpTransport([success_response()])
    provider: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)
    authorization = await provider.refresh(command)
    renewed = PersonalOAuthGrant.model_validate_json(authorization.authorization.get_secret_value())
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url == command.grant.token_endpoint
    expected = {"grant_type": ["refresh_token"], "refresh_token": ["old-refresh"], "resource": [command.grant.resource]}
    if method == "client_secret_basic":
        assert isinstance(request.authentication, BasicOAuthHttpAuthentication)
        assert request.authentication.client_secret == SecretStr("client-secret")
    else:
        expected["client_id"] = ["client"]
        if method == "client_secret_post":
            expected["client_secret"] = ["client-secret"]
    assert parse_qs(request.body.get_secret_value()) == expected
    assert transport.destinations == []
    assert renewed.granted_scopes == ("read",)
    assert renewed.refresh_token == command.grant.refresh_token
    assert renewed.lifetime == ExpiringPersonalToken(expires_at=command.now + timedelta(hours=1))
    for field in ("key", "resource", "issuer", "client_id", "token_endpoint", "redirect_uri", "requested_scopes", "configuration_revision", "client_mode", "token_endpoint_auth_method"):
        assert getattr(renewed, field) == getattr(command.grant, field)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("none", "client_secret_basic", "client_secret_post"))
@pytest.mark.parametrize("uri", ("http://localhost:18010/api/oauth/downstream-mcp/callback", "http://127.0.0.1/callback", "http://[::1]:8080/callback"))
async def test_http_refresh_context_requires_current_local_callback_policy(
    refresh_command: RefreshPersonalOAuth, method: str, uri: str,
) -> None:
    command = refresh_command.model_copy(update={"grant": refresh_command.grant.model_copy(update={"redirect_uri": uri})})
    if method != "none":
        client = PreconfiguredConfidentialOAuthClient.model_validate({
            "issuer_url": command.grant.issuer, "client_id": command.grant.client_id,
            "client_secret": "secret", "token_endpoint_auth_method": method,
        })
        command = command.model_copy(update={
            "policy": command.policy.model_copy(update={"client": client}),
            "grant": command.grant.model_copy(update={"client_mode": client.kind, "token_endpoint_auth_method": method}),
        })
    transport = InMemoryOAuthHttpTransport([success_response()])
    strict: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthRefreshUncertain):
        await strict.refresh(command)
    assert not transport.requests
    local: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.LOCAL_DEVELOPMENT, transport)
    renewed = await local.refresh(command)
    assert PersonalOAuthGrant.model_validate_json(renewed.authorization.get_secret_value()).redirect_uri == uri
    assert len(transport.requests) == 1


@pytest.mark.asyncio
async def test_refresh_can_rotate_refresh_token_and_narrow_scopes(refresh_command: RefreshPersonalOAuth) -> None:
    transport = InMemoryOAuthHttpTransport([success_response(refresh_token="new-refresh", scope="")])
    provider: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)
    result = await provider.refresh(refresh_command)
    renewed = PersonalOAuthGrant.model_validate_json(result.authorization.get_secret_value())
    assert renewed.refresh_token == PresentPersonalRefreshToken(token=SecretStr("new-refresh"))
    assert renewed.granted_scopes == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"scope": "write"}, {"scope": "read write"}, {"refresh_token": ""}, {"refresh_token": "bad\nsecret"},
    {"access_token": "bad token"}, {"access_token": ""}, {"token_type": "MAC"},
    {"expires_in": 0}, {"expires_in": -1}, {"expires_in": None}, {"expires_in": float("inf")},
    {"expires_in": 10**100}, {"expires_in": True}, {"error": "invalid_grant"},
])
async def test_invalid_success_is_uncertain_without_retry(refresh_command: RefreshPersonalOAuth, changes: dict[str, object]) -> None:
    transport = InMemoryOAuthHttpTransport([success_response(**changes)])
    provider: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthRefreshUncertain) as caught:
        await provider.refresh(refresh_command)
    assert caught.value.__context__ is None
    assert len(transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,denied", [
    (400, b'{"error":"invalid_grant"}', True), (401, b'{"error":"invalid_client"}', True),
    (500, b'{"error":"invalid_grant"}', False), (400, b'{"error":"temporarily_unavailable"}', False),
    (400, b'{"error":"invalid_grant","error_description":123}', False),
    (400, b'{"error":"invalid_grant","access_token":"reflected"}', False),
    (400, b'{"error":"invalid_grant","error":"invalid_grant"}', False),
    (200, b'{"access_token":"new-access","token_type":"Bearer"}', False),
    (200, b'not json', False), (302, b'{}', False), (503, b'{}', False),
])
async def test_only_definitive_endpoint_errors_are_denied(
    refresh_command: RefreshPersonalOAuth, status: int, body: bytes, denied: bool,
) -> None:
    transport = InMemoryOAuthHttpTransport([OAuthHttpResponse(status=status, body=body)])
    provider: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthRefreshDenied if denied else PersonalOAuthRefreshUncertain) as caught:
        await provider.refresh(refresh_command)
    assert caught.value.__context__ is None
    assert len(transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"client_id": "different"}, {"issuer": "https://other.example"}, {"configuration_revision": "different"},
    {"requested_scopes": ()}, {"client_mode": "dynamic_public"},
    {"refresh_token": AbsentPersonalRefreshToken()}, {"lifetime": UnknownPersonalTokenLifetime()},
    {"token_endpoint": "https://127.0.0.1/token"}, {"issued_at": datetime(2099, 1, 1, tzinfo=timezone.utc)},
])
async def test_unsupported_bindings_do_not_call_network(refresh_command: RefreshPersonalOAuth, changes: dict[str, object]) -> None:
    transport = InMemoryOAuthHttpTransport([])
    provider: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthRefreshUncertain):
        await provider.refresh(refresh_command.model_copy(update={"grant": refresh_command.grant.model_copy(update=changes)}))
    assert transport.requests == []


class FailingRefreshTransport(InMemoryOAuthHttpTransport):
    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        self.requests.append(command)
        raise TimeoutError("old-refresh new-refresh client-secret")


@pytest.mark.asyncio
async def test_network_failure_has_fixed_error_without_raw_context_or_retry(refresh_command: RefreshPersonalOAuth) -> None:
    transport = FailingRefreshTransport([])
    provider: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthRefreshUncertain) as caught:
        await provider.refresh(refresh_command)
    assert str(caught.value) == "Personal OAuth refresh outcome uncertain"
    assert caught.value.__context__ is None
    assert len(transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 400, 503])
async def test_reflected_credentials_never_reach_debug_logs(
    refresh_command: RefreshPersonalOAuth, public_dns: list[str], caplog: pytest.LogCaptureFixture, status: int,
) -> None:
    caplog.set_level(logging.DEBUG)
    secrets = "old-refresh new-refresh client-secret"
    body = success_response(refresh_token="new-refresh").body if status == 200 else json.dumps({
        "error": "invalid_grant", "error_description": secrets,
    }).encode()
    stream = MemoryStream(
        f"HTTP/1.1 {status} Status\r\nContent-Length: {len(body)}\r\nX-Reflection: {secrets}\r\n\r\n".encode() + body,
    )
    network = MemoryNetwork(stream)
    client = PreconfiguredConfidentialOAuthClient(
        issuer_url=refresh_command.grant.issuer, client_id=refresh_command.grant.client_id,
        token_endpoint_auth_method="client_secret_post", client_secret=SecretStr("client-secret"),
    )
    command = refresh_command.model_copy(update={
        "policy": refresh_command.policy.model_copy(update={"client": client}),
        "grant": refresh_command.grant.model_copy(update={
            "client_mode": client.kind, "token_endpoint_auth_method": client.token_endpoint_auth_method,
        }),
    })
    async with httpcore.AsyncConnectionPool(
        network_backend=PublicAddressNetworkBackend(network), ssl_context=ssl.create_default_context(), retries=0,
    ) as pool:
        provider: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, SafeOAuthHttpTransport(pool))
        if status == 200:
            await provider.refresh(command)
        else:
            with pytest.raises(PersonalOAuthRefreshDenied if status == 400 else PersonalOAuthRefreshUncertain) as caught:
                await provider.refresh(command)
            assert caught.value.__context__ is None
            assert not any(secret in str(caught.value) for secret in secrets.split())
    assert not any(secret in caplog.text for secret in secrets.split())
    assert len(network.targets) == 1
    assert public_dns == ["tokens.example"]
    assert network.targets == [("93.184.216.34", 443)]
    assert stream.server_hostname == "tokens.example"
    assert stream.written.count(b"POST ") == 1


class SlowRefreshTransport(InMemoryOAuthHttpTransport):
    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        self.requests.append(command)
        await anyio.sleep_forever()
        raise AssertionError("Unreachable")


@pytest.mark.asyncio
async def test_command_deadline_bounds_refresh_without_retry(refresh_command: RefreshPersonalOAuth) -> None:
    transport = SlowRefreshTransport([])
    provider: PersonalOAuthRefreshProvider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthRefreshUncertain):
        await provider.refresh(refresh_command.model_copy(update={"timeout_seconds": 0.01}))
    assert len(transport.requests) == 1
