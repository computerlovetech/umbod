import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.error import URLError

import pytest
from fastmcp.server.http import StarletteWithLifespan

from messaging.in_memory import InMemoryEventCheckpointStoreFactory, InMemoryEventCheckpointStoreMessages
from messaging.models import StreamEvent
from umbod.mcp import public_app
from umbod.mcp.settings import MCPAppSettings
from umbod.mcp.telemetry.composition import create_configured_mcp_telemetry
from umbod.mcp.connectors.downstream_mcp.capability_notifications import CapabilityListChangeNotifier
from umbod.mcp.messaging import McpMessagingAdapterFactory
from umbod.mcp.runtime_options import StoreBackedConnectorRuntimeStateSourceStrategy


@pytest.fixture
def context(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setattr(public_app, 'reconcile_openapi_discovery', AsyncMock())
    return SimpleNamespace(
        api_base_url=None,
        source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(),
        settings=SimpleNamespace(endpoints=SimpleNamespace(mcp_base_url='http://test'), mcp=SimpleNamespace(messaging_transport='sql', metrics_port=0, metrics_enabled=False)),
        persistence_runtime=SimpleNamespace(database=object(), readiness=SimpleNamespace(ensure_ready=AsyncMock()), shutdown=AsyncMock()),
        http_app=StarletteWithLifespan(),
        telemetry=create_configured_mcp_telemetry(MCPAppSettings()),
        connector_runtime=SimpleNamespace(connector_tool_mappings=()),
        group_permission_runtime_state=None,
        mcp=SimpleNamespace(
            downstream_mcp_discovery_runtime=Mock(),
            downstream_mcp_discovery_coordinator=SimpleNamespace(reconcile_native_capabilities=AsyncMock(), initialize_native_capabilities=AsyncMock(), stop=Mock()),
            connector_tool_registry=SimpleNamespace(reconcile_all=AsyncMock(), client_notifier=Mock(spec=CapabilityListChangeNotifier)),
        ),
    )


@pytest.fixture
def adapters(monkeypatch: pytest.MonkeyPatch) -> Mock:
    adapters = Mock(spec=McpMessagingAdapterFactory)
    adapters.create_checkpoint_store.return_value = InMemoryEventCheckpointStoreFactory(InMemoryEventCheckpointStoreMessages()).create()
    monkeypatch.setattr(public_app, 'McpMessagingAdapterFactory', Mock(return_value=adapters))
    return adapters


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [URLError('source unavailable'), ValueError('invalid projection')])
async def test_failed_projection_bootstrap_never_enters_ready_lifespan_and_closes_persistence(context: SimpleNamespace, adapters: Mock, failure: Exception) -> None:
    reader = SimpleNamespace(list_after=AsyncMock(side_effect=failure))
    adapters.create_projection_reader.return_value = reader
    app = await public_app.build_starlette_app(context)
    initial_tasks = asyncio.all_tasks()
    with pytest.raises(type(failure)):
        async with app.router.lifespan_context(app):
            pytest.fail('Failed bootstrap must not expose MCP')
    assert not context.mcp.runtime_projection_health.ready
    assert context.mcp.runtime_projection_health.failed
    reader.list_after.assert_awaited_once()
    assert asyncio.all_tasks() == initial_tasks
    context.mcp.downstream_mcp_discovery_coordinator.initialize_native_capabilities.assert_not_awaited()
    context.persistence_runtime.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_cancels_its_projection_consumer_before_closing_persistence(context: SimpleNamespace, adapters: Mock) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def read(sequence: int, limit: int) -> list[StreamEvent]:
        if context.mcp.runtime_projection_health.ready:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        return []

    async def shutdown() -> None:
        assert cancelled.is_set()

    reader = SimpleNamespace(list_after=AsyncMock(side_effect=read))
    adapters.create_projection_reader.return_value = reader
    context.persistence_runtime.shutdown.side_effect = shutdown
    app = await public_app.build_starlette_app(context)
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(), timeout=1)
        assert context.mcp.runtime_projection_health.ready
        context.persistence_runtime.shutdown.assert_not_awaited()
    assert cancelled.is_set()
    context.mcp.downstream_mcp_discovery_coordinator.reconcile_native_capabilities.assert_awaited_once()
    context.persistence_runtime.shutdown.assert_awaited_once()
