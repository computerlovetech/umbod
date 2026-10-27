import asyncio
from dataclasses import replace

import pytest

from tests.umbod.mcp.downstream_mcp_connectors.discovery_query_support import discovery_query_case
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.stores import ConnectorIdQuery, SaveConnectorDefinition
from umbod.mcp.connectors.downstream_mcp.runtime import DownstreamDiscoveryLoader, DownstreamDiscoveryRuntime, DownstreamDiscoverySnapshot, DownstreamDiscoveryUnavailable
from umbod.mcp.connectors.downstream_mcp.runtime.catalog import InMemoryDownstreamDiscoveryRuntime


@pytest.mark.asyncio
async def test_runtime_does_not_serve_an_uninitialized_projection() -> None:
    case = await discovery_query_case(1)
    runtime: DownstreamDiscoveryRuntime = InMemoryDownstreamDiscoveryRuntime(SequenceLoader(case.runtime.capture()))
    with pytest.raises(DownstreamDiscoveryUnavailable):
        runtime.capture()
    await runtime.reconcile()
    assert len(runtime.capture().available_records) == 1


@pytest.mark.asyncio
async def test_failed_reconciliation_closes_discovery_until_successful_retry() -> None:
    case = await discovery_query_case(1)
    previous = case.runtime.capture()
    case.definitions.list.side_effect = RuntimeError("failed read")
    with pytest.raises(RuntimeError, match="failed read"):
        await case.runtime.reconcile()
    with pytest.raises(DownstreamDiscoveryUnavailable):
        await case.provider.list_tools()
    assert len(previous.available_records) == 1
    case.definitions.list.side_effect = None
    await case.runtime.reconcile()
    assert [tool.name for tool in await case.provider.list_tools()] == ["Shared_tool_0"]


@pytest.mark.asyncio
async def test_reconciliation_removes_deleted_names_and_preserves_captured_snapshot() -> None:
    case = await discovery_query_case(1)
    previous = case.runtime.capture()
    await case.definitions.delete(ConnectorIdQuery(connector_id="shared"))
    assert [tool.name for tool in await case.provider.list_tools()] == ["Shared_tool_0"]
    await case.runtime.reconcile()
    assert await case.provider.list_tools() == []
    assert case.runtime.capture().definitions == ()
    assert len(previous.available_records) == 1
    assert await case.provider.configured_tool_name_claims() == ()


@pytest.mark.asyncio
async def test_namespace_reconciliation_reserves_unpublished_personal_definitions() -> None:
    case = await discovery_query_case(1)
    await case.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(connector_id="private", display_name="Private", endpoint_url="https://private.example/mcp", tool_name_prefix="private", authorization_mode="personal")))
    assert not await case.provider.is_personal_tool_name("private_read")
    await case.runtime.reconcile()
    assert await case.provider.is_personal_tool_name("private_read")
    assert [tool.name for tool in await case.provider.list_tools()] == ["Shared_tool_0"]
    await case.definitions.delete(ConnectorIdQuery(connector_id="private"))
    await case.runtime.reconcile()
    assert not await case.provider.is_personal_tool_name("private_read")


@pytest.mark.asyncio
async def test_unpublication_reconciliation_removes_claims_but_not_personal_reservations() -> None:
    case = await discovery_query_case(1)
    await case.publishing.unpublish_connector("shared")
    await case.runtime.reconcile()
    assert await case.provider.list_tools() == []
    assert await case.provider.configured_tool_name_claims() == ()
    assert case.runtime.capture().published_connector_ids == frozenset()


class SequenceLoader(DownstreamDiscoveryLoader):
    def __init__(self, snapshot: DownstreamDiscoverySnapshot) -> None:
        self.snapshot = snapshot
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def load(self) -> DownstreamDiscoverySnapshot:
        self.calls += 1
        if self.calls == 2:
            snapshot = self.snapshot
            self.entered.set()
            await self.release.wait()
            return snapshot
        return self.snapshot


@pytest.mark.asyncio
async def test_overlapping_reconciliations_publish_in_order_without_blocking_reads() -> None:
    case = await discovery_query_case(1)
    initial = case.runtime.capture()
    loader = SequenceLoader(initial)
    runtime: DownstreamDiscoveryRuntime = InMemoryDownstreamDiscoveryRuntime(loader)
    await runtime.reconcile()
    first = asyncio.create_task(runtime.reconcile())
    await loader.entered.wait()
    assert runtime.capture() is initial
    loader.snapshot = replace(initial, available_records=())
    second = asyncio.create_task(runtime.reconcile())
    loader.release.set()
    await asyncio.gather(first, second)
    assert runtime.capture().available_records == ()


@pytest.mark.asyncio
async def test_cancelled_reconciliation_preserves_the_last_complete_snapshot() -> None:
    case = await discovery_query_case(1)
    initial = case.runtime.capture()
    loader = SequenceLoader(initial)
    runtime: DownstreamDiscoveryRuntime = InMemoryDownstreamDiscoveryRuntime(loader)
    await runtime.reconcile()
    pending = asyncio.create_task(runtime.reconcile())
    await loader.entered.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert runtime.capture() is initial
    await runtime.reconcile()
    assert runtime.capture() is initial


@pytest.mark.asyncio
@pytest.mark.parametrize("projection", ("search", "list"))
async def test_public_schema_mutation_does_not_modify_runtime_or_next_caller(projection: str) -> None:
    case = await discovery_query_case(1)
    captured = case.runtime.capture()
    if projection == "search":
        candidate = (await case.provider.eligible_search_candidates())[0]
        candidate.input_schema["properties"]["injected"] = {"type": "string"}
        next_schema = (await case.provider.eligible_search_candidates())[0].input_schema
    else:
        tool = (await case.provider.list_tools())[0]
        tool.parameters["properties"]["injected"] = {"type": "string"}
        next_schema = (await case.provider.list_tools())[0].parameters
    assert "injected" not in next_schema["properties"]
    assert "injected" not in captured.available_records[0].capability.input_schema["properties"]
