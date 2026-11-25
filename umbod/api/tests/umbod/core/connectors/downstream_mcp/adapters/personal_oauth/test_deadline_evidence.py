from contextlib import AbstractContextManager
from tests.support.personal_oauth_applications import InMemoryPersonalOAuthApplicationStore, application_clock
from typing import Optional

import anyio
import httpcore
import pytest

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.failure import OAuthOperationProgress
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.network import SafeOAuthHttpTransport
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.refresh import StoredPersonalOAuthRefreshProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpRequest, OAuthHttpResponse
from umbod.core.connectors.downstream_mcp.personal.oauth.authorization.models import PersonalOAuthProviderFailure
from umbod.core.connectors.downstream_mcp.personal.oauth.refresh.provider_models import PersonalOAuthRefreshUncertain, RefreshPersonalOAuth
from umbod.core.invocation.diagnostics import DownstreamHttpResponse, NoDownstreamResponse
from umbod.core.network import PublicAddressNetworkBackend

from .conftest import ProviderCase, exchange_command, response
from .test_network import FailingEvidenceStream, MemoryNetwork, MemoryStream
from .test_refresh import refresh_command as refresh_command


class RegistrationTransport(InMemoryOAuthHttpTransport):
    def __init__(self, responses: list[OAuthHttpResponse], network: SafeOAuthHttpTransport) -> None:
        super().__init__(responses)
        self.network = network

    async def request_with_progress(self, command: OAuthHttpRequest, progress: OAuthOperationProgress) -> OAuthHttpResponse:
        if self.responses:
            return await self.request(command)
        self.requests.append(command)
        return await self.network.request_with_progress(command, progress)


class CleanupFailureStream(FailingEvidenceStream):
    async def aclose(self) -> None:
        self.closed = True
        raise httpcore.ReadError("cleanup-credential-sentinel")


class StalledBodyStream(MemoryStream):
    def __init__(self, status: int, cleanup_failure: bool) -> None:
        super().__init__(f"HTTP/1.1 {status} Status\r\nContent-Length: 20\r\n\r\n".encode())
        self.cleanup_failure = cleanup_failure

    async def read(self, max_bytes: int, timeout: Optional[float]) -> bytes:
        if self.content:
            return await super().read(max_bytes, timeout)
        await anyio.sleep_forever()
        raise AssertionError("Unreachable")

    async def aclose(self) -> None:
        self.closed = True
        if self.cleanup_failure:
            raise httpcore.ReadError("cleanup-credential-sentinel")


@pytest.mark.asyncio
@pytest.mark.parametrize("status,error,reason", [
    (403, httpcore.ReadTimeout("provider-credential-sentinel"), "provider_rejected"),
    (200, RuntimeError("provider-credential-sentinel"), "unexpected_failure"),
])
async def test_registration_preserves_primary_evidence_through_body_and_cleanup_failures(
    provider_case: ProviderCase, public_dns: list[str], status: int, error: Exception, reason: str,
) -> None:
    stream = CleanupFailureStream(f"HTTP/1.1 {status} Status\r\nContent-Length: 20\r\n\r\n".encode(), error, True)
    network = MemoryNetwork(stream)
    async with httpcore.AsyncConnectionPool(network_backend=PublicAddressNetworkBackend(network), retries=0) as pool:
        transport = RegistrationTransport([
            response(provider_case.resource_metadata), response(provider_case.server_metadata),
        ], SafeOAuthHttpTransport(pool))
        with pytest.raises(PersonalOAuthProviderFailure) as caught:
            await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, transport, applications=InMemoryPersonalOAuthApplicationStore(application_clock), clock=application_clock).prepare(provider_case.preparation)
    assert caught.value.evidence.stage == "registration"
    assert caught.value.evidence.reason == reason
    assert caught.value.evidence.downstream_response == DownstreamHttpResponse(status_code=status)
    assert "credential-sentinel" not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert len(network.targets) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 403])
@pytest.mark.parametrize("cleanup_failure", [False, True])
async def test_refresh_aggregate_deadline_keeps_received_status_and_rejection(
    refresh_command: RefreshPersonalOAuth, public_dns: list[str], status: int, cleanup_failure: bool,
) -> None:
    network = MemoryNetwork(StalledBodyStream(status, cleanup_failure))
    async with httpcore.AsyncConnectionPool(network_backend=PublicAddressNetworkBackend(network), retries=0) as pool:
        provider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, SafeOAuthHttpTransport(pool), applications=InMemoryPersonalOAuthApplicationStore(application_clock), clock=application_clock)
        with pytest.raises(PersonalOAuthRefreshUncertain) as caught:
            await provider.refresh(refresh_command.model_copy(update={"timeout_seconds": 0.01}))
    assert caught.value.evidence.stage == "refresh"
    assert caught.value.evidence.reason == ("provider_rejected" if status == 403 else "timeout")
    assert caught.value.evidence.downstream_response == DownstreamHttpResponse(status_code=status)
    assert "credential-sentinel" not in str(caught.value) + caught.value.evidence.model_dump_json()
    assert len(network.targets) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 403])
async def test_exchange_aggregate_deadline_keeps_received_status_and_rejection(
    provider_case: ProviderCase, public_dns: list[str], monkeypatch: pytest.MonkeyPatch, status: int,
) -> None:
    preparation_transport = InMemoryOAuthHttpTransport([
        response(provider_case.resource_metadata), response(provider_case.server_metadata), response(provider_case.client_metadata),
    ])
    prepared = await DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, preparation_transport, applications=InMemoryPersonalOAuthApplicationStore(application_clock), clock=application_clock).prepare(provider_case.preparation)
    original_fail_after = anyio.fail_after
    deadlines = 0

    def exchange_deadline(delay: float) -> AbstractContextManager[anyio.CancelScope]:
        nonlocal deadlines
        deadlines += 1
        return original_fail_after(0.01 if deadlines == 1 else delay)

    monkeypatch.setattr(anyio, "fail_after", exchange_deadline)
    network = MemoryNetwork(StalledBodyStream(status, True))
    async with httpcore.AsyncConnectionPool(network_backend=PublicAddressNetworkBackend(network), retries=0) as pool:
        provider = DiscoveredPersonalOAuthProvider(CallbackURLPolicy.STRICT, SafeOAuthHttpTransport(pool), applications=InMemoryPersonalOAuthApplicationStore(application_clock), clock=application_clock)
        with pytest.raises(PersonalOAuthProviderFailure) as caught:
            await provider.exchange(exchange_command(provider_case.preparation, prepared))
    assert caught.value.evidence.stage == "token_exchange"
    assert caught.value.evidence.reason == ("provider_rejected" if status == 403 else "timeout")
    assert caught.value.evidence.downstream_response == DownstreamHttpResponse(status_code=status)
    assert len(network.targets) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_failure", [False, True])
@pytest.mark.parametrize("received", [False, True])
async def test_unrelated_caller_cancellation_is_not_converted_to_provider_failure(
    refresh_command: RefreshPersonalOAuth, public_dns: list[str], cleanup_failure: bool, received: bool,
) -> None:
    stream = StalledBodyStream(403, cleanup_failure)
    if not received:
        stream.content = b""
    network = MemoryNetwork(stream)
    async with httpcore.AsyncConnectionPool(network_backend=PublicAddressNetworkBackend(network), retries=0) as pool:
        provider = StoredPersonalOAuthRefreshProvider(CallbackURLPolicy.STRICT, SafeOAuthHttpTransport(pool), applications=InMemoryPersonalOAuthApplicationStore(application_clock), clock=application_clock)
        with anyio.move_on_after(0.01) as caller_scope:
            await provider.refresh(refresh_command)
            pytest.fail("Caller cancellation was swallowed")
    assert caller_scope.cancelled_caught
    assert len(network.targets) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("received", [False, True])
async def test_transport_owned_deadline_preserves_timeout_and_response(
    public_dns: list[str], monkeypatch: pytest.MonkeyPatch, received: bool,
) -> None:
    original_fail_after = anyio.fail_after

    def transport_deadline(delay: float) -> AbstractContextManager[anyio.CancelScope]:
        return original_fail_after(0.01)

    monkeypatch.setattr(anyio, "fail_after", transport_deadline)
    stream = StalledBodyStream(200, True)
    if not received:
        stream.content = b""
    network = MemoryNetwork(stream)
    async with httpcore.AsyncConnectionPool(network_backend=PublicAddressNetworkBackend(network), retries=0) as pool:
        with pytest.raises(PersonalOAuthProviderFailure) as caught:
            await SafeOAuthHttpTransport(pool).request(OAuthHttpRequest(
                method="POST", url="https://issuer.example/token", body="", content_type="",
            ))
    assert caught.value.evidence.reason == "timeout"
    expected = DownstreamHttpResponse(status_code=200) if received else NoDownstreamResponse()
    assert caught.value.evidence.downstream_response == expected
    assert len(network.targets) == 1
