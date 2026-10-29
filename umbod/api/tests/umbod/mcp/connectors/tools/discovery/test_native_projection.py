import asyncio
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP

from umbod.core.capabilities.descriptions import (
    ConnectorCapabilityDescriptionOverrideStore,
    SystemConnectorCapabilityDescriptionOverrideStore,
)
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.configuration import (
    ConnectorCurrentConfigurationStore,
)
from tests.support.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.core.invocation.policy import PermitAllConnectorInvocationPolicy
from umbod.core.publishing import ConnectorPublishingStore
from tests.support.signals import InMemorySignalFailureHandler
from umbod.mcp.connectors.native.tools import InMemoryConnectorToolRuntimeStateStore
from umbod.mcp.connectors.native.tools.deployment_modes import ConnectorToolExposureMode
from umbod.mcp.connectors.native.tools.infrastructure.authorization import UnrestrictedConnectorTools
from umbod.mcp.connectors.native.tools.registration import register_connector_tools
from umbod.mcp.connectors.native.tools.runtime.registry import RuntimeConnectorToolRegistry
from umbod.mcp.signals import McpSignals
from umbod.mcp.signals.execution import SignalToolExecutionPipelineFactory
from tests.umbod.mcp.connectors.tools.test_connector_tool_exposure_mode_acceptance import (
    ConnectorToolExposureMcpBuilder,
    InMemoryConnectorPublishingStore,
)


async def _build_mcp(
    configuration: ConnectorCurrentConfigurationStore,
    publication: ConnectorPublishingStore,
    descriptions: ConnectorCapabilityDescriptionOverrideStore,
    exposure_mode: ConnectorToolExposureMode,
) -> FastMCP:
    builder = ConnectorToolExposureMcpBuilder()
    await configuration.save_current_configuration("slack", builder._configuration())
    await publication.publish_connector("slack")
    signals = McpSignals(InMemorySignalFailureHandler())
    runtime_states = InMemoryConnectorToolRuntimeStateStore()
    runtime_states.save_runtime_state(ConnectorToolRuntimeState(
        key=ConnectorToolRef("slack", "list_readable_channels"), status="enabled",
    ))
    mcp = FastMCP()
    await register_connector_tools(
        mcp,
        connector_registrations=[builder._connector_registration()],
        connector_configuration_store=configuration,
        connector_publishing_store=publication,
        connector_tool_mappings=[builder._tool_mapping()],
        capability_description_overrides=descriptions,
        connector_tool_runtime_state_store=runtime_states,
        signals=signals,
        execution_pipelines=SignalToolExecutionPipelineFactory(
            signals, PermitAllConnectorInvocationPolicy(),
        ),
        connector_tool_exposure_mode=exposure_mode,
    )
    return mcp


async def _cancel_tasks(*tasks: asyncio.Task[None]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)


@pytest.mark.asyncio
async def test_initialized_native_list_and_search_do_not_read_configuration_or_descriptions() -> None:
    configuration = AsyncMock(wraps=InMemoryConnectorCurrentConfigurationStore())
    publication = AsyncMock(wraps=InMemoryConnectorPublishingStore())
    descriptions = AsyncMock(wraps=SystemConnectorCapabilityDescriptionOverrideStore())
    mcp = await _build_mcp(configuration, publication, descriptions, "gateway")
    for reader in (
        configuration.get_current_configuration,
        publication.is_published,
        descriptions.get_many,
    ):
        reader.side_effect = AssertionError("discovery I/O")
    async with Client(mcp) as client:
        tools = await client.list_tools()
        result = await client.call_tool("search_tools", {"query": "readable channels"})
    assert "Slack: Access connector capabilities." in next(
        tool.description for tool in tools if tool.name == "search_tools"
    )
    assert result.is_error is False
    assert len(result.structured_content["matches"]) == 1


@pytest.mark.asyncio
async def test_native_reconcile_removes_unavailable_candidates_without_request_hydration() -> None:
    publication = AsyncMock(wraps=InMemoryConnectorPublishingStore())
    mcp = await _build_mcp(
        InMemoryConnectorCurrentConfigurationStore(), publication,
        SystemConnectorCapabilityDescriptionOverrideStore(), "gateway",
    )
    registry = mcp.connector_tool_registry
    scope = UnrestrictedConnectorTools()
    assert len(await registry.eligible_search_candidates(scope)) == 1
    publication.is_published.return_value = False
    assert len(await registry.eligible_search_candidates(scope)) == 1
    await registry.reconcile_connector("slack")
    publication.is_published.side_effect = AssertionError("request hydration")
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
    command: str,
) -> None:
    published = AsyncMock(wraps=InMemoryConnectorPublishingStore())
    mcp = await _build_mcp(
        InMemoryConnectorCurrentConfigurationStore(), published,
        SystemConnectorCapabilityDescriptionOverrideStore(), "flat",
    )
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
            await asyncio.wait_for(release.wait(), timeout=5)
            return True
        return False

    published.is_published.side_effect = publication
    first = asyncio.create_task(_reconcile(registry, command))
    tasks = [first]
    try:
        await asyncio.wait_for(started.wait(), timeout=5)

        async def reconcile_again() -> None:
            queued.set()
            await registry.reconcile_connector("slack")

        second = asyncio.create_task(reconcile_again())
        tasks.append(second)
        await asyncio.wait_for(queued.wait(), timeout=5)
        assert calls == 1
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
    finally:
        await _cancel_tasks(*tasks)
    assert await registry.eligible_search_candidates(UnrestrictedConnectorTools()) == []
    async with Client(mcp) as client:
        assert "slack_list_readable_channels" not in {tool.name for tool in await client.list_tools()}


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["all", "connector", "runtime", "refresh"])
@pytest.mark.parametrize("failure_source", ["publication", "descriptions"])
async def test_native_read_failure_hides_flat_exposure_and_search_until_retry(
    command: str, failure_source: str,
) -> None:
    publication = AsyncMock(wraps=InMemoryConnectorPublishingStore())
    descriptions = AsyncMock(wraps=SystemConnectorCapabilityDescriptionOverrideStore())
    mcp = await _build_mcp(
        InMemoryConnectorCurrentConfigurationStore(), publication, descriptions, "flat",
    )
    registry = mcp.connector_tool_registry
    if failure_source == "publication":
        reader = publication.is_published
        reader.return_value = True
    else:
        reader = descriptions.get_many
        reader.return_value = (object(),)
    reader.side_effect = RuntimeError("read failed")
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
async def test_cancelled_native_reconcile_preserves_flat_exposure_and_allows_retry() -> None:
    published = AsyncMock(wraps=InMemoryConnectorPublishingStore())
    mcp = await _build_mcp(
        InMemoryConnectorCurrentConfigurationStore(), published,
        SystemConnectorCapabilityDescriptionOverrideStore(), "flat",
    )
    registry = mcp.connector_tool_registry
    started = asyncio.Event()
    release = asyncio.Event()

    async def publication(connector_id: str) -> bool:
        started.set()
        await asyncio.wait_for(release.wait(), timeout=5)
        return False

    published.is_published.side_effect = publication
    task = asyncio.create_task(registry.reconcile_all())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
    finally:
        await _cancel_tasks(task)
    assert len(await registry.eligible_search_candidates(UnrestrictedConnectorTools())) == 1
    async with Client(mcp) as client:
        assert "slack_list_readable_channels" in {tool.name for tool in await client.list_tools()}
        published.is_published.side_effect = None
        published.is_published.return_value = False
        await registry.reconcile_all()
        assert "slack_list_readable_channels" not in {tool.name for tool in await client.list_tools()}
    assert await registry.eligible_search_candidates(UnrestrictedConnectorTools()) == []
