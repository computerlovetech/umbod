from tests.support.personal_oauth_diagnostics import RecordingOAuthFailureObserver
from tests.support.personal_oauth_setup import SETUP_CALLBACK, install_setup_validation
from umbod.core.connectors.downstream_mcp.management import PublishDownstreamConnectorAggregate
from tests.umbod.core.connectors.downstream_mcp.personal_caller_support import captured_personal_caller
import asyncio
import json
from datetime import UTC, datetime, timedelta

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeAuthorizationQuery
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import (
    FinishCallback, ClaimPersonalOAuthAttempt, ClaimedPersonalOAuthAttempt, CompletePersonalOAuthAttempt,
    FailPersonalOAuthAttempt, PersonalOAuthAttemptQuery, PersonalOAuthAttemptView, PublishPersonalOAuthAttempt,
    ReservePersonalOAuthAttempt,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthAttemptStore
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_failure_models import OAuthFailureEvidence
from umbod.core.invocation.diagnostics import DownstreamHttpResponse
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import GenericRoute, PresentCallbackIssuer

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthDestination, OAuthHttpRequest, OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal_connections import PersonalConnectorInventory, PersonalConnectorSelection
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure, PersonalOAuthUnavailable
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_service import PersonalOAuthCallbackService, PersonalOAuthService
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import DynamicPublicOAuthClient, PersonalOAuthSettings, PreconfiguredConfidentialOAuthClient, PreconfiguredPublicOAuthClient, ReplacePersonalOAuthConfiguration
from umbod.core.connectors.downstream_mcp.stores import create_downstream_mcp_stores

from .test_personal_oauth_attempt_persistence import AttemptCase, case as case


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
    await install_setup_validation(case.bundle, "personal")
    await case.bundle.unit_of_work.publish(PublishDownstreamConnectorAggregate(connector_id="personal", native_identities=(), personal_oauth_redirect_uri=SETUP_CALLBACK))
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
        case.clock, case.bundle.personal_oauth_configurations, failures=RecordingOAuthFailureObserver(),
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
    callback = PersonalOAuthCallbackService(recreated.personal_oauth_attempts, DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport), case.clock, failures=RecordingOAuthFailureObserver())
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


class CleanupFailingAttemptStore:
    def __init__(self, wrapped: PersonalOAuthAttemptStore) -> None:
        self._wrapped = wrapped
        self.failures: list[FailPersonalOAuthAttempt] = []

    async def reserve(self, command: ReservePersonalOAuthAttempt) -> PersonalOAuthAttemptView:
        return await self._wrapped.reserve(command)

    async def publish(self, command: PublishPersonalOAuthAttempt) -> PersonalOAuthAttemptView:
        return await self._wrapped.publish(command)

    async def get(self, query: PersonalOAuthAttemptQuery) -> PersonalOAuthAttemptView:
        return await self._wrapped.get(query)

    async def cancel(self, query: PersonalOAuthAttemptQuery) -> PersonalOAuthAttemptView:
        return await self._wrapped.cancel(query)

    async def abort_preparation(self, query: PersonalOAuthAttemptQuery) -> None:
        await self._wrapped.abort_preparation(query)

    async def claim(self, command: ClaimPersonalOAuthAttempt) -> ClaimedPersonalOAuthAttempt:
        return await self._wrapped.claim(command)

    async def complete(self, command: CompletePersonalOAuthAttempt) -> PersonalOAuthAttemptView:
        return await self._wrapped.complete(command)

    async def fail(self, command: FailPersonalOAuthAttempt) -> None:
        self.failures.append(command)
        raise RuntimeError("sentinel-cleanup-secret")

    async def delete_connector(self, connector_id: str) -> None:
        await self._wrapped.delete_connector(connector_id)


@pytest.mark.asyncio
async def test_callback_cleanup_failure_does_not_replace_original_provider_evidence(case: AttemptCase) -> None:
    state, _ = await start_configured(case, "none")
    store = CleanupFailingAttemptStore(case.bundle.personal_oauth_attempts)
    transport = InMemoryOAuthHttpTransport([OAuthHttpResponse(status=403, body=b"sentinel-provider-token")])
    failures = RecordingOAuthFailureObserver()
    callback = PersonalOAuthCallbackService(
        store, DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport), case.clock, failures=failures,
    )

    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await callback.finish(FinishCallback(
            state=SecretStr(state), code=SecretStr("authorization-code"),
            issuer=PresentCallbackIssuer(kind="present", value="https://issuer.example"), error="", scope="read", route=GenericRoute(kind="generic"),
        ))

    evidence = OAuthFailureEvidence(stage="token_exchange", reason="provider_rejected", downstream_response=DownstreamHttpResponse(status_code=403))
    assert caught.value.evidence == evidence
    assert failures.failures == [("personal", evidence)]
    assert len(store.failures) == 1
    assert "sentinel" not in str(caught.value)
    assert len(transport.requests) == 1


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
    callback = PersonalOAuthCallbackService(case.bundle.personal_oauth_attempts, DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, PausingTokenTransport(started, release)), case.clock, failures=RecordingOAuthFailureObserver())
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
    callback = PersonalOAuthCallbackService(case.bundle.personal_oauth_attempts, DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport), case.clock, failures=RecordingOAuthFailureObserver())
    with pytest.raises(PersonalOAuthProviderFailure):
        await callback.finish(FinishCallback(state=SecretStr(state), code=SecretStr("authorization-code"), issuer=PresentCallbackIssuer(kind="present", value="https://issuer.example"), error="", scope=callback_scope, route=GenericRoute(kind="generic")))
    assert transport.requests == []
    assert (await case.bundle.personal_connections.get(case.query.key)).authorization.kind == "unauthorized"
    assert (await case.bundle.personal_oauth_attempts.get(case.query.model_copy(update={"attempt_id": state.split(".", 1)[0]}))).status == "failed"
