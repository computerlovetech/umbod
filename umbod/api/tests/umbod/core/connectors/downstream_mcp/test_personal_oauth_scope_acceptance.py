"""Acceptance tests for issue #37: approved scopes stay enforced through authorization and refresh.

Runs the real OAuth adapters and persistent stores against local provider fixtures through the
injectable in-memory HTTP transport. All unrelated OAuth checks are satisfied so each scenario
isolates the granted scopes.
"""

import json
from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr

from tests.umbod.core.connectors.downstream_mcp.personal_caller_support import captured_personal_caller
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.refresh import StoredPersonalOAuthRefreshProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalConnectorInventory, PersonalConnectorSelection
from umbod.core.connectors.downstream_mcp.personal_connections.authorization_models import (
    ExpiringPersonalToken, PersonalOAuthGrant, PresentPersonalRefreshToken,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import GenericRoute, PresentCallbackIssuer
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import FinishCallback, PersonalOAuthProviderFailure
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_service import PersonalOAuthCallbackService, PersonalOAuthService
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_provider_models import (
    PersonalOAuthRefreshUncertain, RefreshPersonalOAuth,
)
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import (
    DynamicPublicOAuthClient, PersonalOAuthPolicy, PersonalOAuthSettings, PreconfiguredPublicOAuthClient,
    ReplacePersonalOAuthConfiguration,
)

from .test_personal_oauth_attempt_persistence import AttemptCase, case as case

ISSUER = "https://issuer.example"
CALLBACK = "https://umbod.example/api/oauth/downstream-mcp/callback"
READ = "documents.read"


def _json(value: dict[str, object]) -> OAuthHttpResponse:
    return OAuthHttpResponse(status=200, body=json.dumps(value).encode())


async def pending_authorization_requesting_read(case: AttemptCase) -> str:
    """Given a user has a pending authorization requesting "documents.read"."""
    await case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
        connector_id="personal", expected_revision="legacy",
        settings=PersonalOAuthSettings(requested_scopes=(READ,), client=DynamicPublicOAuthClient()),
    ))
    inventory = AsyncMock(spec=PersonalConnectorInventory)
    inventory.get.return_value = PersonalConnectorSelection(
        connector_id="personal", display_name="Document service", capability_description="Documents",
        enabled=True, has_authorization=False,
    )
    transport = InMemoryOAuthHttpTransport([
        _json({"resource": case.command.endpoint_url, "authorization_servers": [ISSUER]}),
        _json({
            "issuer": ISSUER, "authorization_endpoint": ISSUER + "/authorize", "token_endpoint": ISSUER + "/token",
            "registration_endpoint": ISSUER + "/register", "code_challenge_methods_supported": ["S256"],
            "grant_types_supported": ["authorization_code"], "response_types_supported": ["code"],
            "token_endpoint_auth_methods_supported": ["none"], "authorization_response_iss_parameter_supported": True,
        }),
        _json({
            "client_id": "registered-client", "redirect_uris": [CALLBACK], "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"], "response_types": ["code"], "scope": READ,
        }),
    ])
    service = PersonalOAuthService(
        captured_personal_caller(case.query.key.principal, ("team",)), inventory, case.bundle.definitions,
        case.bundle.personal_connections, case.bundle.personal_oauth_attempts,
        DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport), CALLBACK,
        case.clock, case.bundle.personal_oauth_configurations, diagnostics=Mock(),
    )
    started = await service.start("personal")
    assert started.attempt.status == "pending"
    query = parse_qs(urlsplit(started.authorization_url.get_secret_value()).query)
    assert query["scope"] == [READ]
    return query["state"][0]


async def complete_callback(case: AttemptCase, state: str, granted_scope: str) -> InMemoryOAuthHttpTransport:
    """When the user completes the authorization callback with all other checks satisfied."""
    transport = InMemoryOAuthHttpTransport([_json({
        "access_token": "user-access-token", "token_type": "Bearer", "expires_in": 3600, "scope": granted_scope,
    })])
    callback = PersonalOAuthCallbackService(
        case.bundle.personal_oauth_attempts, DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport), case.clock,
    )
    await callback.finish(FinishCallback(
        state=SecretStr(state), code=SecretStr("authorization-code"),
        issuer=PresentCallbackIssuer(kind="present", value=ISSUER), error="", scope="",
        route=GenericRoute(kind="generic"),
    ))
    return transport


@pytest.mark.asyncio
async def test_matching_token_completes_authorization(case: AttemptCase) -> None:
    state = await pending_authorization_requesting_read(case)

    await complete_callback(case, state, READ)

    connection = await case.bundle.personal_connections.get(case.query.key)
    assert connection.authorization.kind == "authorized"
    saved = json.loads(connection.authorization.authorization.get_secret_value())
    assert saved["granted_scopes"] == [READ]


@pytest.mark.asyncio
async def test_token_cannot_grant_permissions_beyond_configured_request(case: AttemptCase) -> None:
    state = await pending_authorization_requesting_read(case)

    with pytest.raises(PersonalOAuthProviderFailure):
        await complete_callback(case, state, READ + " documents.write")

    assert (await case.bundle.personal_connections.get(case.query.key)).authorization.kind == "unauthorized"
    attempt = await case.bundle.personal_oauth_attempts.get(case.query.model_copy(update={"attempt_id": state.split(".", 1)[0]}))
    assert attempt.status == "failed"


@pytest.mark.asyncio
async def test_refresh_cannot_expand_previously_granted_permissions(case: AttemptCase) -> None:
    now = case.clock()
    policy = PersonalOAuthPolicy(
        revision="configured", requested_scopes=(READ,),
        client=PreconfiguredPublicOAuthClient(issuer_url=ISSUER, client_id="configured-client"),
    )
    grant = PersonalOAuthGrant(
        version=2, key=case.query.key, issuer=ISSUER, resource=case.command.endpoint_url,
        client_id="configured-client", token_endpoint=ISSUER + "/token", redirect_uri=CALLBACK,
        client_mode="preconfigured_public", token_endpoint_auth_method="none",
        requested_scopes=(READ,), granted_scopes=(READ,), configuration_revision="configured",
        issued_at=now - timedelta(hours=2), lifetime=ExpiringPersonalToken(expires_at=now - timedelta(hours=1)),
        access_token=SecretStr("old-access"), refresh_token=PresentPersonalRefreshToken(token=SecretStr("old-refresh")),
    )
    transport = InMemoryOAuthHttpTransport([_json({
        "access_token": "expanded-access", "token_type": "Bearer", "expires_in": 3600,
        "scope": READ + " documents.write",
    })])
    provider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)

    with pytest.raises(PersonalOAuthRefreshUncertain):
        await provider.refresh(RefreshPersonalOAuth(policy=policy, now=now, timeout_seconds=20, grant=grant))

    assert len(transport.requests) == 1
    assert grant.granted_scopes == (READ,)
