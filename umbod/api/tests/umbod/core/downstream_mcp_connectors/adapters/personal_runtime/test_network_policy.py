from .contracts import LOOKUP_FINGERPRINT
import ssl
from datetime import datetime, timezone

import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.personal_runtime import FastMCPPersonalMcpTransport
from umbod.core.connectors.downstream_mcp.personal_connections.models import CanonicalPrincipal
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_models import PersonalRuntimeLimits, PersonalRuntimeTarget, PersonalRuntimeUnavailable, PersonalToolCall
from umbod.core.connectors.downstream_mcp.personal_connections.runtime_ports import PersonalMcpTransport

from .conftest import ScriptedNetwork, ScriptedResolver, make_transport


@pytest.mark.asyncio
async def test_each_owner_gets_fresh_bearer_session_and_dns_pin(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    resolver = ScriptedResolver()
    transport = make_transport(limits, network, resolver)
    other = target.model_copy(update={"access_token": SecretStr("bob-secret-token"), "key": target.key.model_copy(update={"principal": CanonicalPrincipal(namespace="test", subject="bob")})})
    for owner in (target, other):
        inventory = await transport.list_tools(owner)
        assert inventory.tools[0].identity.downstream_name == "lookup"
        assert inventory.tools[0].output_schema_status == "absent"
        result = await transport.call_tool(PersonalToolCall(target=owner, tool_name="lookup", expected_fingerprint=LOOKUP_FINGERPRINT, arguments={"value": 1}))
        assert result.result["content"] == [{"type": "text", "text": "done"}]
    initializations = [headers["authorization"] for _, headers, body in network.requests if body.get("method") == "initialize"]
    assert initializations == ["bearer alice-secret-token"] * 2 + ["bearer bob-secret-token"] * 2
    assert set(network.connections) == {"8.8.8.8"}
    assert set(network.sni) == {"public.example"}
    assert len(resolver.lookups) == len(network.connections)
    assert all(headers["host"] == "public.example" for _, headers, _ in network.requests)
    assert all("cookie" not in headers for _, headers, _ in network.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("addresses", [("127.0.0.1",), ("8.8.8.8", "10.0.0.1"), ("::ffff:8.8.8.8",), ("169.254.169.254",), ()])
async def test_nonpublic_or_mixed_dns_denied_before_tcp(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, addresses: tuple[str, ...]) -> None:
    transport = make_transport(limits, network, ScriptedResolver(addresses))
    with pytest.raises(PersonalRuntimeUnavailable, match="^Personal MCP unavailable$"):
        await transport.list_tools(target)
    assert network.connections == []


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://public.example/mcp", "https://user:pass@public.example/mcp", "https://public.example/mcp#fragment"])
async def test_invalid_resource_is_rejected(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, url: str) -> None:
    transport = make_transport(limits, network, ScriptedResolver())
    with pytest.raises(PersonalRuntimeUnavailable):
        await transport.list_tools(target.model_copy(update={"endpoint_url": url}))
    assert network.requests == []


@pytest.mark.asyncio
async def test_injected_verified_context_reaches_tls_unchanged(target: PersonalRuntimeTarget, limits: PersonalRuntimeLimits, network: ScriptedNetwork, monkeypatch: pytest.MonkeyPatch) -> None:
    context = ssl.create_default_context()
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/must-not-replace-injected-context")
    transport: PersonalMcpTransport = FastMCPPersonalMcpTransport(
        limits, lambda: datetime.now(timezone.utc), ScriptedResolver(), lambda: network, context,
    )
    await transport.list_tools(target)
    assert network.tls_contexts
    assert all(actual is context for actual in network.tls_contexts)


@pytest.mark.parametrize("disable_certificates", [False, True])
def test_unverified_tls_context_is_rejected(limits: PersonalRuntimeLimits, network: ScriptedNetwork, disable_certificates: bool) -> None:
    context = ssl.create_default_context()
    context.check_hostname = False
    if disable_certificates:
        context.verify_mode = ssl.CERT_NONE
    with pytest.raises(ValueError, match="Personal MCP requires verified TLS"):
        FastMCPPersonalMcpTransport(limits, lambda: datetime.now(timezone.utc), ScriptedResolver(), lambda: network, context)
