from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from pydantic import SecretStr

from tests.persistence_runtime import create_inmemory_runtime
from umbod.core.activation import ActivationStatus, CapabilityRef
from umbod.core.capabilities.descriptions import SystemConnectorCapabilityDescriptionOverrideStore
from umbod.core.connectors.downstream_mcp.models import (
    DiscoveredPrompt,
    DiscoveredResource,
    DiscoveredResourceTemplate,
    DiscoveredToolWithoutOutputSchema,
    DiscoverySucceeded,
    OAuthConnectorDefinition,
    OAuthCredentialState,
    ToolCatalogSnapshot,
    ToolIdentity,
)
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.stores import (
    DownstreamMcpStores,
    ReplaceToolCatalog,
    SaveConnectorDefinition,
    SaveCredential,
    create_downstream_mcp_stores,
)
from umbod.core.invocation import PermitAllConnectorInvocationPolicy
from umbod.mcp.downstream_mcp_connectors import (
    ConnectorAwareDownstreamMcpToolProvider,
    UnrestrictedDownstreamToolPermissionPolicy,
)
from umbod.mcp.downstream_mcp_connectors.discovery_execution import (
    ConnectorDiscoveryExecutionDependencies,
    ConnectorDiscoveryExecutor,
)
from umbod.mcp.logging import McpToolInvocationCompleted
from umbod.mcp.metrics import InMemoryMcpMetricsRecorder


class NullInvocationLogger:
    def record_tool_invocation_completed(self, event: McpToolInvocationCompleted) -> None:
        return None


class RejectingDownstreamFactory:
    def __init__(self) -> None:
        self.created: list[DiscoverDownstreamTools] = []

    def create(self, command: DiscoverDownstreamTools) -> Client:
        self.created.append(command)
        raise AssertionError("Downstream access must not occur")


class RejectingDiscovery:
    def __init__(self) -> None:
        self.calls: list[DiscoverDownstreamTools] = []

    async def discover(self, command: DiscoverDownstreamTools) -> DiscoverySucceeded:
        self.calls.append(command)
        raise AssertionError("Downstream discovery must not occur")


@dataclass(frozen=True)
class OwnershipFixture:
    stores: DownstreamMcpStores
    provider: ConnectorAwareDownstreamMcpToolProvider
    factory: RejectingDownstreamFactory

    async def make_personal(self) -> None:
        await self.stores.definitions.save(SaveConnectorDefinition(
            definition=OAuthConnectorDefinition(
                connector_id="alpha",
                display_name="Alpha",
                tool_name_prefix="alpha",
                endpoint_url="https://alpha.example/mcp",
                authorization_mode="personal",
            )
        ))


@pytest_asyncio.fixture
async def ownership() -> OwnershipFixture:
    stores = await create_downstream_mcp_stores("test-secret", create_inmemory_runtime().database)
    await stores.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(
        connector_id="alpha", display_name="Alpha", tool_name_prefix="alpha", endpoint_url="https://alpha.example/mcp"
    )))
    await stores.credentials.save(SaveCredential(credential=OAuthCredentialState(
        connector_id="alpha", authorization=SecretStr("admin-authorization-canary")
    )))
    await stores.catalogs.replace(ReplaceToolCatalog(snapshot=ToolCatalogSnapshot(
        connector_id="alpha",
        discovered_at=datetime.now(UTC),
        tools=(DiscoveredToolWithoutOutputSchema(
            identity=ToolIdentity(connector_id="alpha", downstream_name="lookup"),
            title="Lookup", description="Lookup", input_schema={"type": "object"},
        ),),
        prompts=(DiscoveredPrompt(name="summarize", title="Summarize", description=""),),
        resources=(DiscoveredResource(name="fixed", title="Fixed", uri="data://alpha/fixed", description=""),),
        resource_templates=(DiscoveredResourceTemplate(name="item", title="Item", uri_template="data://alpha/items/{item}", description=""),),
    )))
    await stores.publishing.publish_connector("alpha")
    for kind, key in (
        ("tool", "lookup"),
        ("prompt", "summarize"),
        ("resource", "data://alpha/fixed"),
        ("resource_template", "data://alpha/items/{item}"),
    ):
        await stores.activations.set_status(CapabilityRef(
            connector_kind="downstream_mcp", connector_id="alpha",
            capability_kind=kind, capability_key=key,
        ), ActivationStatus.ENABLED)
    factory = RejectingDownstreamFactory()
    provider = ConnectorAwareDownstreamMcpToolProvider(
        definitions=stores.definitions, credentials=stores.credentials,
        catalogs=stores.catalogs, publishing=stores.publishing, activations=stores.activations,
        client_factory=factory, permission_policy=UnrestrictedDownstreamToolPermissionPolicy(),
        connector_scope="", capability_description_overrides=SystemConnectorCapabilityDescriptionOverrideStore(),
        tool_invocation_logger=NullInvocationLogger(),
        metrics_recorder=InMemoryMcpMetricsRecorder(), invocation_policy=PermitAllConnectorInvocationPolicy(),
    )
    return OwnershipFixture(stores, provider, factory)


@pytest.mark.asyncio
async def test_personal_definition_is_hidden_from_all_capability_lists_and_search(ownership: OwnershipFixture) -> None:
    await ownership.make_personal()
    public = FastMCP("public", providers=[ownership.provider])
    async with Client(public) as client:
        assert await client.list_tools() == []
        assert await client.list_prompts() == []
        assert await client.list_resources() == []
        assert await client.list_resource_templates() == []
    assert await ownership.provider.eligible_search_candidates() == []
    assert ownership.factory.created == []


@pytest.mark.asyncio
async def test_personal_definition_cannot_be_invoked_directly(ownership: OwnershipFixture) -> None:
    await ownership.make_personal()
    with pytest.raises(ToolError, match="not available"):
        await ownership.provider.execute_tool("alpha_lookup", {})
    assert ownership.factory.created == []


@pytest.mark.asyncio
async def test_previously_materialized_tool_rechecks_ownership(ownership: OwnershipFixture) -> None:
    cached_tool = await ownership.provider.get_tool("alpha_lookup")
    assert cached_tool is not None
    await ownership.make_personal()
    public = FastMCP("public")

    @public.tool
    async def invoke_cached() -> ToolResult:
        return await cached_tool.run({})

    async with Client(public) as client:
        result = await client.call_tool_mcp("invoke_cached", {})
    assert result.is_error
    assert ownership.factory.created == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["prompt", "resource", "template"])
async def test_previously_materialized_native_capability_rechecks_ownership(ownership: OwnershipFixture, kind: str) -> None:
    prompts = await ownership.provider.list_prompts()
    resources = await ownership.provider.list_resources()
    templates = await ownership.provider.list_resource_templates()
    await ownership.make_personal()
    with pytest.raises(ToolError, match="not available"):
        if kind == "prompt":
            await prompts[0].render({})
        elif kind == "resource":
            await resources[0].read()
        else:
            await templates[0].create_resource("data://alpha/items/one", {"item": "one"})
    assert ownership.factory.created == []


@pytest.mark.asyncio
async def test_materialized_template_resource_rechecks_ownership_before_cached_read(
    ownership: OwnershipFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    downstream = FastMCP("downstream")

    @downstream.resource("data://alpha/items/{item}")
    def item_resource(item: str) -> str:
        return "shared-content-" + item

    def create_backend(command: DiscoverDownstreamTools) -> Client:
        ownership.factory.created.append(command)
        return Client(downstream)

    monkeypatch.setattr(ownership.factory, "create", create_backend)
    template = (await ownership.provider.list_resource_templates())[0]
    public = FastMCP("public")

    @public.tool
    async def verify_cached_resource() -> str:
        resource = await template.create_resource("data://alpha/items/one", {"item": "one"})
        await ownership.make_personal()
        with pytest.raises(ToolError, match="not available"):
            await resource.read()
        return "denied"

    async with Client(public) as client:
        result = await client.call_tool_mcp("verify_cached_resource", {})
    assert not result.is_error
    assert result.content[0].text == "denied"
    assert len(ownership.factory.created) == 1


@pytest.mark.asyncio
async def test_background_discovery_skips_personal_definition(ownership: OwnershipFixture) -> None:
    await ownership.make_personal()
    discovery = RejectingDiscovery()
    executor = ConnectorDiscoveryExecutor(ConnectorDiscoveryExecutionDependencies(
        definitions=ownership.stores.definitions,
        credentials=ownership.stores.credentials,
        discovery=discovery,
    ))
    assert await executor.execute("alpha") is None
    assert discovery.calls == []
