from tests.umbod.core.downstream_mcp_connectors.personal_caller_support import captured_personal_caller
import asyncio
import json
from datetime import UTC, datetime, timedelta

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import FinishCallback
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import GenericRoute, PresentCallbackIssuer

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthDestination, OAuthHttpRequest, OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalConnectorInventory, PersonalConnectorSelection
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure, PersonalOAuthUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_service import PersonalOAuthCallbackService, PersonalOAuthService
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import DynamicPublicOAuthClient, PersonalOAuthSettings, PreconfiguredConfidentialOAuthClient, PreconfiguredPublicOAuthClient, ReplacePersonalOAuthConfiguration
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores

from test_personal_oauth_attempt_persistence import AttemptCase, case as case


def response(value: dict[str, object]) -> OAuthHttpResponse:
    return OAuthHttpResponse(status=200, body=json.dumps(value).encode())


async def start_configured(case: AttemptCase, method: str) -> tuple[str, str]:
    configured_client = (
        PreconfiguredPublicOAuthClient(issuer_url="https://issuer.example", client_id="configured-client")
        if method == "none" else PreconfiguredConfidentialOAuthClient(
            issuer_url="https://issuer.example", client_id="configured-client", client_secret="client-secret",
            token_endpoint_auth_method=method,
        )
    )
    configured = await case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
        connector_id="personal", expected_revision="legacy", settings=PersonalOAuthSettings(requested_scopes=("read",), client=configured_client),
    ))
    inventory = AsyncMock(spec=PersonalConnectorInventory)
    inventory.get.return_value = PersonalConnectorSelection(connector_id="personal", display_name="Personal", capability_description="Personal access", enabled=True, has_authorization=False)
    transport = InMemoryOAuthHttpTransport([
        response({"resource": case.command.endpoint_url, "authorization_servers": ["https://issuer.example"]}),
        response({
            "issuer": "https://issuer.example", "authorization_endpoint": "https://issuer.example/authorize", "token_endpoint": "https://issuer.example/token",
            "code_challenge_methods_supported": ["S256"], "grant_types_supported": ["authorization_code"], "response_types_supported": ["code"],
            "token_endpoint_auth_methods_supported": [method], "authorization_response_iss_parameter_supported": True,
        }),
    ])
    service = PersonalOAuthService(
        captured_personal_caller(case.query.key.principal, ("team",)), inventory, case.bundle.definitions,
        case.bundle.personal_connections, case.bundle.personal_oauth_attempts,
        DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport), "https://umbod.example/api/oauth/downstream-mcp/callback",
        case.clock, case.bundle.personal_oauth_configurations,
    )
    started = await service.start("personal")
    state = parse_qs(urlsplit(started.authorization_url.get_secret_value()).query)["state"][0]
    assert len(transport.requests) == 2
    return state, configured.policy.revision


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("none", "client_secret_basic", "client_secret_post"))
async def test_configured_workflow_completes_on_recreated_worker_with_scoped_callback(case: AttemptCase, method: str) -> None:
    state, revision = await start_configured(case, method)
    recreated = await create_downstream_mcp_stores("test-secret", case.database)
    transport = InMemoryOAuthHttpTransport([response({"access_token": "user-access-token", "token_type": "Bearer", "expires_in": 3600})])
    callback = PersonalOAuthCallbackService(recreated.personal_oauth_attempts, DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport), case.clock)
    await callback.finish(FinishCallback(state=SecretStr(state), code=SecretStr("authorization-code"), issuer=PresentCallbackIssuer(kind="present", value="https://issuer.example"), error="", scope="read", route=GenericRoute(kind="generic")))
    connection = await recreated.personal_connections.get(case.query.key)
    assert connection.authorization.kind == "authorized"
    saved = json.loads(connection.authorization.authorization.get_secret_value())
    assert saved["granted_scopes"] == ["read"]
    assert saved["configuration_revision"] == revision
    target = await recreated.personal_runtime_authorizations.resolve(PersonalRuntimeAuthorizationQuery(key=case.query.key, group_ids=("team",), now=datetime.now(UTC)))
    assert target.access_token.get_secret_value() == "user-access-token"
    assert target.expires_at == datetime.fromisoformat(saved["issued_at"]) + timedelta(hours=1)
    assert len(transport.requests) == 1
    assert "client-secret" not in connection.authorization.authorization.get_secret_value()


class PausingTokenTransport:
    def __init__(self, started: asyncio.Event, release: asyncio.Event) -> None:
        self._started = started
        self._release = release

    async def validate_destination(self, command: OAuthDestination) -> None:
        raise AssertionError("Callback must not rediscover or validate browser destination")

    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        assert command.url == "https://issuer.example/token"
        self._started.set()
        await self._release.wait()
        return response({"access_token": "late-access-token", "token_type": "Bearer"})


@pytest.mark.asyncio
async def test_policy_change_during_exchange_cannot_install_old_authorization(case: AttemptCase) -> None:
    state, revision = await start_configured(case, "client_secret_basic")
    started, release = asyncio.Event(), asyncio.Event()
    callback = PersonalOAuthCallbackService(case.bundle.personal_oauth_attempts, DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, PausingTokenTransport(started, release)), case.clock)
    task = asyncio.create_task(callback.finish(FinishCallback(state=SecretStr(state), code=SecretStr("authorization-code"), issuer=PresentCallbackIssuer(kind="present", value="https://issuer.example"), error="", scope="read", route=GenericRoute(kind="generic"))))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        await case.bundle.personal_oauth_configurations.replace(ReplacePersonalOAuthConfiguration(
            connector_id="personal", expected_revision=revision,
            settings=PersonalOAuthSettings(requested_scopes=(), client=DynamicPublicOAuthClient()),
        ))
    finally:
        release.set()
    with pytest.raises((PersonalOAuthProviderFailure, PersonalOAuthUnavailable)):
        await task
    connection = await case.bundle.personal_connections.get(case.query.key)
    assert connection.enabled is True
    assert connection.authorization.kind == "unauthorized"


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_scope", ("unapproved", "read\twrite"))
async def test_callback_scope_escalation_or_invalid_syntax_never_exchanges_code(case: AttemptCase, callback_scope: str) -> None:
    state, _ = await start_configured(case, "client_secret_basic")
    transport = InMemoryOAuthHttpTransport([])
    callback = PersonalOAuthCallbackService(case.bundle.personal_oauth_attempts, DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport), case.clock)
    with pytest.raises(PersonalOAuthProviderFailure):
        await callback.finish(FinishCallback(state=SecretStr(state), code=SecretStr("authorization-code"), issuer=PresentCallbackIssuer(kind="present", value="https://issuer.example"), error="", scope=callback_scope, route=GenericRoute(kind="generic")))
    assert transport.requests == []
    assert (await case.bundle.personal_connections.get(case.query.key)).authorization.kind == "unauthorized"
    assert (await case.bundle.personal_oauth_attempts.get(case.query.model_copy(update={"attempt_id": state.split(".", 1)[0]}))).status == "failed"
