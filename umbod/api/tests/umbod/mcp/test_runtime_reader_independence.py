from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp.server.http import StarletteWithLifespan

from messaging.in_memory import InMemoryEventCheckpointStoreFactory, InMemoryEventCheckpointStoreMessages
from tests.support.messaging import InMemoryEventStreamFactory
from umbod.core.activation import ActivationStatus, ActivationStore
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.core.permissions.ports import GroupPermissionReader
from umbod.mcp import public_app
from umbod.mcp.connectors.downstream_mcp.capability_notifications import CapabilityListChangeNotifier
from umbod.mcp.connectors.downstream_mcp.coordinator import DownstreamDiscoveryCoordinator
from umbod.mcp.connectors.native.tools import InMemoryConnectorToolRuntimeStateStore
from umbod.mcp.connectors.native.tools.runtime.registry import RuntimeConnectorToolRegistry
from umbod.mcp.messaging import McpMessagingAdapterFactory, RuntimeProjectionHealth
from umbod.mcp.runtime_options import ConnectorRuntimeStateSourceStrategy, HttpConnectorRuntimeStateSourceStrategy, LocalConnectorRuntimeStateSourceStrategy, StoreBackedConnectorRuntimeStateSourceStrategy


def runtime_source(source: str) -> ConnectorRuntimeStateSourceStrategy:
    if source == "http":
        return HttpConnectorRuntimeStateSourceStrategy()
    if source == "local":
        return LocalConnectorRuntimeStateSourceStrategy(Mock(), Mock())
    return StoreBackedConnectorRuntimeStateSourceStrategy()


def runtime_context(source: str, transport: str, api_url: str) -> SimpleNamespace:
    registry = Mock(spec=RuntimeConnectorToolRegistry)
    registry.client_notifier = Mock(spec=CapabilityListChangeNotifier)
    activations = Mock(spec=ActivationStore)
    activations.get_status.return_value = ActivationStatus.ENABLED
    return SimpleNamespace(
        api_base_url=api_url or None,
        source_strategy=runtime_source(source),
        settings=SimpleNamespace(endpoints=SimpleNamespace(mcp_base_url="http://test"), mcp=SimpleNamespace(messaging_transport=transport, metrics_enabled=False, metrics_port=0)),
        persistence_runtime=SimpleNamespace(database=object(), readiness=SimpleNamespace(ensure_ready=AsyncMock()), shutdown=AsyncMock()),
        http_app=StarletteWithLifespan(),
        metrics_recorder=Mock(),
        group_permission_runtime_state=InMemoryGroupConnectorToolPermissions(group_claim_fields=("groups",)),
        connector_tool_runtime_state_store=InMemoryConnectorToolRuntimeStateStore(),
        connector_runtime=SimpleNamespace(connector_tool_mappings=(SimpleNamespace(connector_id="connector", operation_name="read"),)),
        mcp=SimpleNamespace(
            runtime_projection_health=RuntimeProjectionHealth(),
            downstream_mcp_discovery_coordinator=Mock(spec=DownstreamDiscoveryCoordinator),
            downstream_mcp_discovery_runtime=Mock(),
            connector_tool_registry=registry,
            connector_prompt_registry=SimpleNamespace(reconcile_all=AsyncMock()),
            connector_resource_registry=SimpleNamespace(reconcile_all=AsyncMock()),
            capability_activation_store=activations,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ("http", "sql"))
@pytest.mark.parametrize("source", ("http", "database", "local"))
async def test_event_transport_does_not_select_runtime_data_readers(monkeypatch: pytest.MonkeyPatch, source: str, transport: str) -> None:
    context = runtime_context(source, transport, "http://data-service")
    events = InMemoryEventStreamFactory("closed").create()
    checkpoints = InMemoryEventCheckpointStoreFactory(InMemoryEventCheckpointStoreMessages()).create()
    adapters = Mock(spec=McpMessagingAdapterFactory)
    adapters.create_projection_reader.return_value = events
    adapters.create_checkpoint_store.return_value = checkpoints
    adapter_factory = Mock(return_value=adapters)
    monkeypatch.setattr(public_app, "McpMessagingAdapterFactory", adapter_factory)
    monkeypatch.setattr(public_app, "reconcile_openapi_discovery", AsyncMock())
    native_sync = SimpleNamespace(sync_all=AsyncMock())
    monkeypatch.setattr(public_app, "runtime_state_synchronizer_options", Mock(return_value=object()))
    monkeypatch.setattr(public_app, "create_connector_runtime_state_synchronizer", Mock(return_value=native_sync))
    key = ConnectorToolRef("connector", "read")
    http_tools = SimpleNamespace(get_runtime_state=AsyncMock(return_value=ConnectorToolRuntimeState(key=key, status="enabled")))
    tool_reader_factory = Mock(return_value=http_tools)
    monkeypatch.setattr(public_app, "HttpConnectorToolRuntimeStateReader", tool_reader_factory)
    database_permissions = Mock(spec=GroupPermissionReader)
    database_permissions.list_all_group_permissions.return_value = []
    http_permissions = Mock(spec=GroupPermissionReader)
    http_permissions.list_all_group_permissions.return_value = []
    database_reader_factory = Mock(return_value=database_permissions)
    http_reader_factory = Mock(return_value=http_permissions)
    monkeypatch.setattr(public_app, "DatabaseGroupPermissionReader", database_reader_factory)
    monkeypatch.setattr(public_app, "HttpGroupPermissionReader", http_reader_factory)

    app = await public_app.build_starlette_app(context)
    async with app.router.lifespan_context(app):
        adapter_factory.assert_called_once_with(transport, "http://data-service", context.persistence_runtime.database)
        assert context.mcp.runtime_projection_health.ready
        assert context.connector_tool_runtime_state_store.get_runtime_state(key).status == "enabled"
        if source == "http":
            native_sync.sync_all.assert_awaited_once()
            tool_reader_factory.assert_called_once_with("http://data-service")
            http_permissions.list_all_group_permissions.assert_awaited_once()
            database_reader_factory.assert_not_called()
            context.mcp.capability_activation_store.get_status.assert_not_called()
        else:
            if source == "local":
                native_sync.sync_all.assert_awaited_once()
            else:
                native_sync.sync_all.assert_not_awaited()
            tool_reader_factory.assert_not_called()
            database_permissions.list_all_group_permissions.assert_awaited_once()
            http_reader_factory.assert_not_called()
            context.mcp.capability_activation_store.get_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_http_event_adapter_does_not_require_an_api_url(monkeypatch: pytest.MonkeyPatch) -> None:
    context = runtime_context("database", "independent-adapter", "")
    context.group_permission_runtime_state = None
    events = InMemoryEventStreamFactory("closed").create()
    checkpoints = InMemoryEventCheckpointStoreFactory(InMemoryEventCheckpointStoreMessages()).create()
    adapters = Mock(spec=McpMessagingAdapterFactory)
    adapters.create_projection_reader.return_value = events
    adapters.create_checkpoint_store.return_value = checkpoints
    adapter_factory = Mock(return_value=adapters)
    monkeypatch.setattr(public_app, "McpMessagingAdapterFactory", adapter_factory)
    monkeypatch.setattr(public_app, "reconcile_openapi_discovery", AsyncMock())

    app = await public_app.build_starlette_app(context)
    async with app.router.lifespan_context(app):
        adapter_factory.assert_called_once_with("independent-adapter", "", context.persistence_runtime.database)
        assert context.mcp.runtime_projection_health.ready
