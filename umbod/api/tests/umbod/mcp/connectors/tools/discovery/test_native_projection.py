import asyncio
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client

from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.mcp.connectors.native.tools.runtime.registry import RuntimeConnectorToolRegistry
from umbod.mcp.connectors.native.tools.infrastructure.authorization import UnrestrictedConnectorTools
from tests.umbod.mcp.connectors.tools.test_connector_tool_exposure_mode_acceptance import (
    ConnectorToolExposureMcpBuilder,
    InMemoryConnectorPublishingStore,
)


@pytest.mark.asyncio
async def test_initialized_native_list_and_search_do_not_read_configuration_or_descriptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = await ConnectorToolExposureMcpBuilder().in_gateway_mode().build()
    for store, method in (
        (InMemoryConnectorCurrentConfigurationStore, "get_current_configuration"),
        (InMemoryConnectorPublishingStore, "is_published"),
        (mcp.capability_description_overrides, "get_many"),
    ):
        monkeypatch.setattr(store, method, AsyncMock(side_effect=AssertionError("discovery I/O")))
    async with Client(mcp) as client:
        tools = await client.list_tools()
        result = await client.call_tool("search_tools", {"query": "readable channels"})
    assert "Slack: Access connector capabilities." in next(
        tool.description for tool in tools if tool.name == "search_tools"
    )
    assert result.is_error is False
    assert len(result.structured_content["matches"]) == 1


@pytest.mark.asyncio
async def test_native_reconcile_removes_unavailable_candidates_without_request_hydration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = await ConnectorToolExposureMcpBuilder().in_gateway_mode().build()
    registry = mcp.connector_tool_registry
    scope = UnrestrictedConnectorTools()
    assert len(await registry.eligible_search_candidates(scope)) == 1
    published = AsyncMock(return_value=False)
    monkeypatch.setattr(InMemoryConnectorPublishingStore, "is_published", published)
    assert len(await registry.eligible_search_candidates(scope)) == 1
    await registry.reconcile_connector("slack")
    published.side_effect = AssertionError("request hydration")
    assert await registry.eligible_search_candidates(scope) == []


async def _reconcile(registry: RuntimeConnectorToolRegistry, command: str) -> None:
    if command == "all":
        await registry.reconcile_all()
    elif command == "connector":
        await registry.reconcile_connector("slack")
    elif command == "runtime":
        await registry.reconcile_runtime_state(ConnectorToolRef("slack", "list_readable_channels"))
    else:
        await registry.refresh_discovery()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["all", "connector", "runtime", "refresh"])
async def test_native_reconciliation_serializes_mapping_and_search_publication(
    monkeypatch: pytest.MonkeyPatch, command: str,
) -> None:
    mcp = await ConnectorToolExposureMcpBuilder().build()
    registry = mcp.connector_tool_registry
    started = asyncio.Event()
    release = asyncio.Event()
    queued = asyncio.Event()
    calls = 0

    async def publication(connector_id: str) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
            return True
        return False

    monkeypatch.setattr(InMemoryConnectorPublishingStore, "is_published", AsyncMock(side_effect=publication))
    first = asyncio.create_task(_reconcile(registry, command))
    await started.wait()

    async def reconcile_again() -> None:
        queued.set()
        await registry.reconcile_connector("slack")

    second = asyncio.create_task(reconcile_again())
    await queued.wait()
    assert calls == 1
    release.set()
    await asyncio.gather(first, second)
    assert await registry.eligible_search_candidates(UnrestrictedConnectorTools()) == []
    async with Client(mcp) as client:
        assert "slack_list_readable_channels" not in {tool.name for tool in await client.list_tools()}


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["all", "connector", "runtime", "refresh"])
@pytest.mark.parametrize("failure_source", ["publication", "descriptions"])
async def test_native_read_failure_hides_flat_exposure_and_search_until_retry(
    monkeypatch: pytest.MonkeyPatch, command: str, failure_source: str,
) -> None:
    mcp = await ConnectorToolExposureMcpBuilder().build()
    registry = mcp.connector_tool_registry
    reader = AsyncMock(side_effect=RuntimeError("read failed"))
    if failure_source == "publication":
        monkeypatch.setattr(InMemoryConnectorPublishingStore, "is_published", reader)
        reader.return_value = True
    else:
        monkeypatch.setattr(mcp.capability_description_overrides, "get_many", reader)
        reader.return_value = (object(),)
    with pytest.raises(RuntimeError, match="read failed"):
        await _reconcile(registry, command)
    assert await registry.eligible_search_candidates(UnrestrictedConnectorTools()) == []
    async with Client(mcp) as client:
        assert "slack_list_readable_channels" not in {tool.name for tool in await client.list_tools()}
        reader.side_effect = None
        await _reconcile(registry, command)
        assert "slack_list_readable_channels" in {tool.name for tool in await client.list_tools()}
    assert len(await registry.eligible_search_candidates(UnrestrictedConnectorTools())) == 1


@pytest.mark.asyncio
async def test_cancelled_native_reconcile_preserves_flat_exposure_and_allows_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = await ConnectorToolExposureMcpBuilder().build()
    registry = mcp.connector_tool_registry
    started = asyncio.Event()
    release = asyncio.Event()

    async def publication(connector_id: str) -> bool:
        started.set()
        await release.wait()
        return False

    published = AsyncMock(side_effect=publication)
    monkeypatch.setattr(InMemoryConnectorPublishingStore, "is_published", published)
    task = asyncio.create_task(registry.reconcile_all())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(await registry.eligible_search_candidates(UnrestrictedConnectorTools())) == 1
    async with Client(mcp) as client:
        assert "slack_list_readable_channels" in {tool.name for tool in await client.list_tools()}
        published.side_effect = None
        published.return_value = False
        await registry.reconcile_all()
        assert "slack_list_readable_channels" not in {tool.name for tool in await client.list_tools()}
    assert await registry.eligible_search_candidates(UnrestrictedConnectorTools()) == []
