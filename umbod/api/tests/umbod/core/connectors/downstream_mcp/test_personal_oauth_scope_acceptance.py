"""Acceptance tests for issue #37: approved scopes stay enforced through authorization and refresh.

Runs the real OAuth adapters and persistent stores against local provider fixtures through the
injectable in-memory HTTP transport. All unrelated OAuth checks are satisfied so each scenario
isolates the granted scopes.
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr

from tests.umbod.core.connectors.downstream_mcp.personal_caller_support import captured_personal_caller
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_models import PersonalRefreshUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_service import PersonalRefreshService
from umbod.core.connectors.downstream_mcp.stores.personal_refresh import EncryptedPersonalRefreshStore
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.refresh import StoredPersonalOAuthRefreshProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalConnectorInventory, PersonalConnectorSelection
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import GenericRoute, PresentCallbackIssuer
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import (
    FinishCallback, PersonalOAuthAttemptView, PersonalOAuthProviderFailure, PersonalOAuthScopeMismatch,
    ReservePersonalOAuthAttempt,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthAttemptStore
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_service import PersonalOAuthCallbackService, PersonalOAuthService
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import (
    DynamicPublicOAuthClient, PersonalOAuthSettings, PreconfiguredPublicOAuthClient,
    ReplacePersonalOAuthConfiguration,
)

from .test_personal_oauth_attempt_persistence import AttemptCase, case as case

ISSUER = "https://issuer.example"
CALLBACK = "https://umbod.example/api/oauth/downstream-mcp/callback"
READ = "documents.read"


def _json(value: dict[str, object]) -> OAuthHttpResponse:
    return OAuthHttpResponse(status=200, body=json.dumps(value).encode())


def oauth_service(
    case: AttemptCase, *, registered_scope: str, preconfigured: bool = False,
    attempts: PersonalOAuthAttemptStore | None = None,
) -> PersonalOAuthService:
    """Real discovery and registration against local fixtures that satisfy every non-scope OAuth check."""
    inventory = AsyncMock(spec=PersonalConnectorInventory)
    inventory.get.return_value = PersonalConnectorSelection(
        connector_id="personal", display_name="Document service", capability_description="Documents",
        enabled=True, has_authorization=False,
    )
    responses = [
        _json({"resource": case.command.endpoint_url, "authorization_servers": [ISSUER]}),
        _json({
            "issuer": ISSUER, "authorization_endpoint": ISSUER + "/authorize", "token_endpoint": ISSUER + "/token",
            "registration_endpoint": ISSUER + "/register", "code_challenge_methods_supported": ["S256"],
            "grant_types_supported": ["authorization_code", "refresh_token"], "response_types_supported": ["code"],
            "token_endpoint_auth_methods_supported": ["none"], "authorization_response_iss_parameter_supported": True,
        }),
        _json({
            "client_id": "registered-client", "redirect_uris": [CALLBACK], "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
            "scope": registered_scope,
        }),
    ]
    transport = InMemoryOAuthHttpTransport(responses[:2] if preconfigured else responses)
    return PersonalOAuthService(
        captured_personal_caller(case.query.key.principal, ("team",)), inventory, case.bundle.definitions,
        case.bundle.personal_connections, attempts or case.bundle.personal_oauth_attempts,
        DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport), CALLBACK,
        case.clock, case.bundle.personal_oauth_configurations, diagnostics=Mock(),
    )


async def configure_scopes(case: AttemptCase, scopes: tuple[str, ...], *, preconfigured: bool = False) -> None:
    client = (
        PreconfiguredPublicOAuthClient(issuer_url=ISSUER, client_id="configured-client")
        if preconfigured else DynamicPublicOAuthClient()
    )
    await case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
        connector_id="personal", expected_revision="legacy",
        settings=PersonalOAuthSettings(requested_scopes=scopes, client=client),
    ))


async def pending_authorization_requesting_read(case: AttemptCase, *, preconfigured: bool = False) -> str:
    """Given a user has a pending authorization requesting "documents.read".

    Dynamic registration is the default; a preconfigured public client is used where refresh is required,
    because dynamically registered clients are never refreshed.
    """
    await configure_scopes(case, (READ,), preconfigured=preconfigured)
    started = await oauth_service(case, registered_scope=READ, preconfigured=preconfigured).start("personal")
    assert started.attempt.status == "pending"
    query = parse_qs(urlsplit(started.authorization_url.get_secret_value()).query)
    assert query["scope"] == [READ]
    return query["state"][0]


class RecordingAttempts:
    """Delegates to the real attempt store and records the attempt IDs the service reserves."""

    def __init__(self, store: PersonalOAuthAttemptStore) -> None:
        self._store = store
        self.reserved: list[str] = []

    def __getattr__(self, name: str) -> object:
        return getattr(self._store, name)

    async def reserve(self, command: ReservePersonalOAuthAttempt) -> PersonalOAuthAttemptView:
        self.reserved.append(command.attempt_id)
        return await self._store.reserve(command)


async def complete_callback(case: AttemptCase, state: str, granted_scope: str) -> InMemoryOAuthHttpTransport:
    """When the user completes the authorization callback with all other checks satisfied."""
    transport = InMemoryOAuthHttpTransport([_json({
        "access_token": "user-access-token", "refresh_token": "user-refresh-token", "token_type": "Bearer",
        "expires_in": 3600, "scope": granted_scope,
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
async def test_scope_mismatch_retains_failed_attempt_and_publishes_no_pending_authorization(case: AttemptCase) -> None:
    # Given a personal connector has no requested scopes and the provider registers "documents.read".
    await configure_scopes(case, ())
    attempts = RecordingAttempts(case.bundle.personal_oauth_attempts)

    # When a client starts personal sign-in.
    with pytest.raises(PersonalOAuthScopeMismatch):
        await oauth_service(case, registered_scope=READ, attempts=attempts).start("personal")

    # Then the one reserved attempt is retained as failed and never became pending.
    assert len(attempts.reserved) == 1
    attempt = await case.bundle.personal_oauth_attempts.get(case.query.model_copy(update={"attempt_id": attempts.reserved[0]}))
    assert attempt.status == "failed"
    assert (await case.bundle.personal_connections.get(case.query.key)).authorization.kind == "unauthorized"


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
    # Given a personal connection was authorized with only "documents.read".
    await complete_callback(case, await pending_authorization_requesting_read(case, preconfigured=True), READ)
    before = await case.bundle.personal_connections.get(case.query.key)
    assert json.loads(before.authorization.authorization.get_secret_value())["granted_scopes"] == [READ]
    case.clock.now = datetime.now(UTC) + timedelta(hours=2)  # the access token has expired
    # And the provider will return a refreshed token granting "documents.read documents.write".
    transport = InMemoryOAuthHttpTransport([_json({
        "access_token": "expanded-access-token", "refresh_token": "expanded-refresh-token", "token_type": "Bearer",
        "expires_in": 3600, "scope": READ + " documents.write",
    })])
    inventory = AsyncMock(spec=PersonalConnectorInventory)
    refresh = PersonalRefreshService(
        captured_personal_caller(case.query.key.principal, ("team",)), inventory,
        EncryptedPersonalRefreshStore(case.database, AuthenticatedTextCipher("test-secret"), case.clock),
        StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport), case.clock,
    )

    # When the connection's authorization is refreshed, then Umbod rejects the refreshed token.
    with pytest.raises(PersonalRefreshUnavailable):
        await refresh.refresh("personal")

    # And the connection does not gain "documents.write".
    assert len(transport.requests) == 1
    after = await case.bundle.personal_connections.get(case.query.key)
    stored = after.authorization.authorization.get_secret_value()
    assert "documents.write" not in stored
    assert "expanded-access-token" not in stored
    assert json.loads(stored)["granted_scopes"] == [READ]
