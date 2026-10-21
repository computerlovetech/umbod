from collections.abc import Iterator
from contextlib import contextmanager
from typing import Optional

import anyio
import httpcore
import pytest

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.factory import configured_personal_oauth_provider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.network import PublicAddressNetworkBackend, SafeOAuthHttpTransport
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.provider import DiscoveredPersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import InMemoryOAuthHttpTransport, OAuthHttpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_models import (
    PersonalOAuthProviderFailure,
    PersonalOAuthProviderUnsupported,
    PreparePersonalOAuth,
)
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthProvider

from .conftest import response
from .test_network import MemoryNetwork, MemoryStream, request


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["authorization_endpoint", "token_endpoint", "registration_endpoint"])
@pytest.mark.parametrize("query", [
    "scope=read", "client_id=attacker", "redirect_uri=https://attacker.example",
    "state=attacker", "code_challenge=attacker", "code_challenge_method=plain",
    "resource=https://attacker.example", "grant_type=client_credentials", "benign=value",
])
async def test_discovered_endpoints_cannot_inject_parameters(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object], server_metadata: dict[str, object],
    field: str, query: str,
) -> None:
    server_metadata[field] = str(server_metadata[field]) + "?" + query
    transport = InMemoryOAuthHttpTransport(responses=[response(resource_metadata), response(server_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(transport=transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)
    assert len(transport.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("authority", ["127.0.0.1", "10.0.0.1", "[::1]", "[::ffff:93.184.216.34]", "[::ffff:127.0.0.1]"])
async def test_browser_authorization_cannot_target_private_or_mapped_literals(
    preparation: PreparePersonalOAuth, resource_metadata: dict[str, object], server_metadata: dict[str, object], authority: str,
) -> None:
    server_metadata["authorization_endpoint"] = "https://" + authority + "/authorize"
    transport = InMemoryOAuthHttpTransport(responses=[response(resource_metadata), response(server_metadata)])
    provider: PersonalOAuthProvider = DiscoveredPersonalOAuthProvider(transport=transport)
    with pytest.raises(PersonalOAuthProviderUnsupported):
        await provider.prepare(preparation)
    assert len(transport.requests) == 2


@pytest.mark.asyncio
async def test_factory_private_endpoint_fails_without_dns(
    preparation: PreparePersonalOAuth, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_dns(host: str, port: int, *, type: int) -> list[object]:
        raise AssertionError("DNS must not run for a private literal")

    monkeypatch.setattr(anyio, "getaddrinfo", unexpected_dns)
    async with configured_personal_oauth_provider() as provider:
        with pytest.raises(PersonalOAuthProviderUnsupported) as caught:
            await provider.prepare(preparation.model_copy(update={"endpoint_url": "https://127.0.0.1/mcp"}))
    assert str(caught.value) == "Personal OAuth provider is unsupported"


@pytest.mark.asyncio
async def test_whole_response_timeout_is_bounded_and_post_is_not_retried(
    monkeypatch: pytest.MonkeyPatch, public_dns: list[str],
) -> None:
    class SlowStream(MemoryStream):
        async def read(self, max_bytes: int, timeout: Optional[float]) -> bytes:
            await anyio.sleep_forever()
            return b""

    real_fail_after = anyio.fail_after
    budgets: list[Optional[float]] = []

    @contextmanager
    def short_deadline(delay: Optional[float]) -> Iterator[anyio.CancelScope]:
        budgets.append(delay)
        with real_fail_after(0.01) as scope:
            yield scope

    monkeypatch.setattr(anyio, "fail_after", short_deadline)
    network = MemoryNetwork(stream=SlowStream(content=b""))
    async with httpcore.AsyncConnectionPool(network_backend=PublicAddressNetworkBackend(backend=network), retries=0) as pool:
        transport: OAuthHttpTransport = SafeOAuthHttpTransport(pool=pool)
        with pytest.raises(PersonalOAuthProviderFailure) as caught:
            await transport.request(request("https://issuer.example/token"))
    assert str(caught.value) == "Personal OAuth provider request failed"
    assert budgets[0] == 20
    assert len(network.targets) == 1
