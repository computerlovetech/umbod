from contextlib import AbstractContextManager

import anyio
import httpcore
import pytest
from pydantic import ValidationError

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.refresh import StoredPersonalOAuthRefreshProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpRequest, OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_failure_models import OAuthEvidenceError, OAuthFailureEvidence, oauth_failure_evidence
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_provider_models import PersonalOAuthRefreshDenied, PersonalOAuthRefreshUncertain, RefreshPersonalOAuth
from umbod.core.invocation.diagnostics import DownstreamHttpResponse, NoDownstreamResponse

from .conftest import ProviderCase, exchange_command, response
from .test_refresh import refresh_command as refresh_command


SENTINEL = "credential-token-client-secret-authorization-code"


class FailedTransport(InMemoryOAuthHttpTransport):
    def __init__(self, error: Exception) -> None:
        super().__init__([])
        self.error = error

    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        self.requests.append(command)
        raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 429, 503])
@pytest.mark.parametrize("stage", ["discovery", "registration"])
async def test_prepare_preserves_rejection_stage_and_status(provider_case: ProviderCase, status: int, stage: str) -> None:
    prefix = [] if stage == "discovery" else [response(provider_case.resource_metadata), response(provider_case.server_metadata)]
    transport = InMemoryOAuthHttpTransport([*prefix, OAuthHttpResponse(status=status, body=SENTINEL.encode())])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await provider.prepare(provider_case.preparation)
    assert caught.value.evidence.model_dump() == {
        "stage": stage, "reason": "provider_rejected",
        "downstream_response": {"kind": "http_response", "status_code": status},
    }
    assert SENTINEL not in str(caught.value)
    assert len(transport.requests) == len(prefix) + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,reason", [(401, SENTINEL.encode(), "provider_rejected"), (200, SENTINEL.encode(), "invalid_response"), (201, b'{}', "invalid_response")])
async def test_exchange_retains_only_current_response_evidence(provider_case: ProviderCase, status: int, body: bytes, reason: str) -> None:
    preparation_transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata), response(provider_case.client_metadata),
    ])
    prepared = await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, preparation_transport).prepare(provider_case.preparation)
    transport = InMemoryOAuthHttpTransport([OAuthHttpResponse(status=status, body=body)])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await provider.exchange(exchange_command(provider_case.preparation, prepared))
    assert caught.value.evidence.stage == "token_exchange"
    assert caught.value.evidence.reason == reason
    assert caught.value.evidence.downstream_response == DownstreamHttpResponse(status_code=status)
    assert SENTINEL not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert len(transport.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error,reason", [(TimeoutError(SENTINEL), "timeout"), (httpcore.ReadTimeout(SENTINEL), "timeout"), (httpcore.ConnectError(SENTINEL), "network_failure"), (OSError(SENTINEL), "network_failure"), (RuntimeError(SENTINEL), "unexpected_failure"), (TypeError(SENTINEL), "unexpected_failure")])
async def test_refresh_classifies_failures_without_secrets_or_retry(refresh_command: RefreshPersonalOAuth, error: Exception, reason: str) -> None:
    transport = FailedTransport(error)
    provider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthRefreshUncertain) as caught:
        await provider.refresh(refresh_command)
    assert caught.value.evidence.stage == "refresh"
    assert caught.value.evidence.reason == reason
    assert caught.value.evidence.downstream_response == NoDownstreamResponse()
    assert SENTINEL not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert caught.value.__context__ is None
    assert len(transport.requests) == 1


@pytest.mark.parametrize("error_type", [PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported, PersonalOAuthRefreshDenied, PersonalOAuthRefreshUncertain])
def test_legacy_exception_text_is_never_preserved(error_type: type[OAuthEvidenceError]) -> None:
    error = error_type(SENTINEL)
    assert SENTINEL not in str(error) + error.evidence.model_dump_json()
    assert oauth_failure_evidence(error, "token_exchange") == error.evidence


class SlowRegistrationTransport(InMemoryOAuthHttpTransport):
    async def request(self, command: OAuthHttpRequest) -> OAuthHttpResponse:
        if self.responses:
            return await super().request(command)
        self.requests.append(command)
        await anyio.sleep_forever()
        raise AssertionError("Unreachable")


@pytest.mark.asyncio
async def test_aggregate_preparation_deadline_keeps_registration_stage(provider_case: ProviderCase, monkeypatch: pytest.MonkeyPatch) -> None:
    fail_after = anyio.fail_after

    def preparation_deadline(delay: float) -> AbstractContextManager[anyio.CancelScope]:
        return fail_after(0.01 if delay == 60 else delay)

    monkeypatch.setattr(anyio, "fail_after", preparation_deadline)
    transport = SlowRegistrationTransport([response(provider_case.resource_metadata), response(provider_case.server_metadata)])
    provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport)
    with pytest.raises(PersonalOAuthProviderFailure) as caught:
        await provider.prepare(provider_case.preparation)
    assert caught.value.evidence.stage == "registration"
    assert caught.value.evidence.reason == "timeout"
    assert caught.value.evidence.downstream_response == NoDownstreamResponse()
    assert len(transport.requests) == 3


def test_failure_evidence_is_immutable_and_bounded() -> None:
    evidence = OAuthFailureEvidence(stage="refresh", reason="timeout", downstream_response=NoDownstreamResponse())
    with pytest.raises(ValidationError):
        evidence.stage = "discovery"
    with pytest.raises(ValidationError):
        DownstreamHttpResponse(status_code=600)
    with pytest.raises(ValidationError):
        OAuthFailureEvidence.model_validate({**evidence.model_dump(), "secret": SENTINEL})
