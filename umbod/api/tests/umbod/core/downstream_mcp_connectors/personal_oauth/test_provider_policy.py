import json
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import BasicOAuthHttpAuthentication, InMemoryOAuthHttpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported, PreparePersonalOAuth
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import DynamicPublicOAuthClient, PersonalOAuthPolicy, PreconfiguredConfidentialOAuthClient, PreconfiguredPublicOAuthClient

from .conftest import exchange_command, response


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("none", "client_secret_basic", "client_secret_post"))
@pytest.mark.parametrize("scope_mode", ("omitted", "empty", "narrow", "full", "excess", "malformed"))
async def test_static_clients_resume_without_registration_and_enforce_granted_scopes(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object],
    server_metadata: dict[str, object], method: str, scope_mode: str,
) -> None:
    client_id = "client:+% ä"
    secret = "private:+% ö"
    client = (
        PreconfiguredPublicOAuthClient(issuer_url=str(server_metadata["issuer"]), client_id=client_id)
        if method == "none" else
        PreconfiguredConfidentialOAuthClient(issuer_url=str(server_metadata["issuer"]), client_id=client_id, client_secret=secret, token_endpoint_auth_method=method)
    )
    policy = PersonalOAuthPolicy(revision="configured-revision", requested_scopes=("write", "read"), client=client)
    preparation = preparation.model_copy(update={"policy": policy})
    server_metadata.pop("registration_endpoint")
    server_metadata["token_endpoint_auth_methods_supported"] = [method]
    server_metadata["scopes_supported"] = ["unrelated.advertisement"]
    transport = InMemoryOAuthHttpTransport([response(resource_metadata), response(server_metadata)])
    port: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(transport)
    prepared = await port.prepare(preparation)
    assert len(transport.requests) == 2
    assert parse_qs(urlsplit(prepared.authorization_url.get_secret_value()).query)["scope"] == ["read write"]
    assert secret not in prepared.authorization_url.get_secret_value()
    assert secret not in prepared.context.get_secret_value()
    token: dict[str, object] = {"access_token": "access-token", "token_type": "Bearer"}
    scopes = {"empty": "", "narrow": "read", "full": "write read", "excess": "admin", "malformed": "read\twrite"}
    if scope_mode != "omitted":
        token["scope"] = scopes[scope_mode]
    exchange_transport = InMemoryOAuthHttpTransport([response(token)])
    resumed: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(exchange_transport)
    command = exchange_command(preparation, prepared)
    if scope_mode in ("excess", "malformed"):
        with pytest.raises(PersonalOAuthProviderFailure):
            await resumed.exchange(command)
    else:
        authorization = await resumed.exchange(command)
        saved = json.loads(authorization.authorization.get_secret_value())
        expected = {"omitted": ["read", "write"], "empty": [], "narrow": ["read"], "full": ["read", "write"]}
        assert saved["granted_scopes"] == expected[scope_mode]
        assert saved["configuration_revision"] == "configured-revision"
        assert secret not in authorization.authorization.get_secret_value()
    request = exchange_transport.requests[0]
    form = parse_qs(request.body.get_secret_value())
    assert form["resource"] == [preparation.endpoint_url]
    if method == "client_secret_basic":
        assert isinstance(request.authentication, BasicOAuthHttpAuthentication)
        assert request.authentication.client_id.get_secret_value() == client_id
        assert request.authentication.client_secret.get_secret_value() == secret
        assert "client_id" not in form and "client_secret" not in form
    else:
        assert request.authentication.kind == "none"
        assert form["client_id"] == [client_id]
        assert (form.get("client_secret") == [secret]) is (method == "client_secret_post")
    assert secret not in repr(request)


@pytest.mark.asyncio
async def test_configured_issuer_mismatch_fails_before_issuer_discovery(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object],
) -> None:
    policy = PersonalOAuthPolicy(revision="revision", requested_scopes=(), client=PreconfiguredConfidentialOAuthClient(
        issuer_url="https://trusted.example", client_id="client", client_secret="private-secret", token_endpoint_auth_method="client_secret_basic",
    ))
    port_transport = InMemoryOAuthHttpTransport([response(resource_metadata)])
    port: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(port_transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await port.prepare(preparation.model_copy(update={"policy": policy}))
    assert len(port_transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("registration_scope", ("omitted", "read write", "read", "admin"))
async def test_dynamic_registration_requests_only_admin_scopes_and_checks_returned_policy(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object],
    server_metadata: dict[str, object], client_metadata: dict[str, object], registration_scope: str,
) -> None:
    preparation = preparation.model_copy(update={"policy": PersonalOAuthPolicy(revision="scoped", requested_scopes=("read", "write"), client=DynamicPublicOAuthClient())})
    if registration_scope != "omitted":
        client_metadata["scope"] = registration_scope
    transport = InMemoryOAuthHttpTransport([response(resource_metadata), response(server_metadata), response(client_metadata)])
    port: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(transport)
    if registration_scope in ("read", "admin"):
        with pytest.raises(PersonalOAuthProviderUnsupported):
            await port.prepare(preparation)
    else:
        await port.prepare(preparation)
    assert json.loads(transport.requests[-1].body.get_secret_value())["scope"] == "read write"


@pytest.mark.asyncio
async def test_missing_authentication_metadata_defaults_to_basic_for_configured_clients(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object], server_metadata: dict[str, object],
) -> None:
    server_metadata.pop("token_endpoint_auth_methods_supported")
    server_metadata.pop("registration_endpoint")
    preparation = preparation.model_copy(update={"policy": PersonalOAuthPolicy(
        revision="basic", requested_scopes=(), client=PreconfiguredConfidentialOAuthClient(
            issuer_url=str(server_metadata["issuer"]), client_id="client", client_secret="secret", token_endpoint_auth_method="client_secret_basic",
        ),
    )})
    transport = InMemoryOAuthHttpTransport([response(resource_metadata), response(server_metadata)])
    port: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(transport)
    await port.prepare(preparation)
    assert len(transport.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", (("policy_revision", "stale"), ("requested_scopes", ["admin"]), ("client_id", "changed-client"), ("token_endpoint_auth_method", "client_secret_post")))
async def test_policy_and_client_bindings_reject_context_changes_before_token_request(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object], server_metadata: dict[str, object],
    client_metadata: dict[str, object], field: str, value: object,
) -> None:
    transport = InMemoryOAuthHttpTransport([response(resource_metadata), response(server_metadata), response(client_metadata)])
    port: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(transport)
    prepared = await port.prepare(preparation)
    context = json.loads(prepared.context.get_secret_value())
    context[field] = value
    changed = prepared.model_copy(update={"context": SecretStr(json.dumps(context))})
    with pytest.raises(PersonalOAuthProviderFailure):
        await port.exchange(exchange_command(preparation, changed))
    assert len(transport.requests) == 3
