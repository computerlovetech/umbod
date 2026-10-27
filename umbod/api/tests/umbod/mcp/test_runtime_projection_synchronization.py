import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from messaging.in_memory import InMemoryEventCheckpointStoreFactory, InMemoryEventCheckpointStoreMessages, InMemoryEventStreamFactory
from messaging.models import MessagingEvent, StreamEvent
from messaging.ports import EventCheckpointStore, EventStream
from umbod.core.connectors.downstream_mcp.models import NoAuthConnectorDefinition
from umbod.mcp.connectors.downstream_mcp.runtime import DownstreamDiscoveryRuntime, DownstreamDiscoverySnapshot
from umbod.mcp.messaging import RuntimeProjectionHealth, RuntimeProjectionSynchronizer
from umbod.mcp.public_app import DynamicPublicMcpDispatcher
from umbod.mcp import public_app
from umbod.mcp.runtime_options import StoreBackedConnectorRuntimeStateSourceStrategy


@pytest.fixture
def events() -> EventStream:
    return InMemoryEventStreamFactory('closed').create()


@pytest.fixture
def checkpoints() -> EventCheckpointStore:
    return InMemoryEventCheckpointStoreFactory(InMemoryEventCheckpointStoreMessages()).create()


def _synchronizer(events: EventStream, checkpoints: EventCheckpointStore, reconcile: Callable[[], Awaitable[None]], health: RuntimeProjectionHealth) -> RuntimeProjectionSynchronizer:
    return RuntimeProjectionSynchronizer(events, checkpoints, reconcile, health, interval_seconds=1.0, batch_limit=1)


@pytest.mark.asyncio
async def test_two_live_workers_independently_replay_and_apply_changes(events: EventStream, checkpoints: EventCheckpointStore) -> None:
    await events.append(MessagingEvent(event_type='connector.discovery.changed', subject='connector'))
    first_reconcile = AsyncMock()
    second_reconcile = AsyncMock()
    first_health = RuntimeProjectionHealth()
    second_health = RuntimeProjectionHealth()
    first = _synchronizer(events, checkpoints, first_reconcile, first_health)
    second = _synchronizer(events, checkpoints, second_reconcile, second_health)

    await first.bootstrap()
    await second.bootstrap()
    await events.append(MessagingEvent(event_type='connector.publication.changed', subject='connector'))
    await first.poll_once()
    await second.poll_once()

    assert first_health.last_applied_sequence == second_health.last_applied_sequence == 2
    assert first_reconcile.await_count == second_reconcile.await_count == 2


@pytest.mark.asyncio
async def test_bootstrap_fences_many_historical_pages_before_one_hydration_and_replays_loading_mutation(events: EventStream, checkpoints: EventCheckpointStore) -> None:
    for _ in range(7):
        await events.append(MessagingEvent(event_type='connector.discovery.changed', subject='connector'))
    health = RuntimeProjectionHealth()
    calls: list[int] = []

    async def reconcile() -> None:
        calls.append(len(calls))
        if len(calls) == 1:
            await events.append(MessagingEvent(event_type='connector.discovery.changed', subject='connector'))

    synchronizer = RuntimeProjectionSynchronizer(events, checkpoints, reconcile, health, interval_seconds=1.0, batch_limit=2)
    await synchronizer.bootstrap()
    assert calls == [0, 1]
    assert health.last_applied_sequence == 8
    assert health.ready


@pytest.mark.asyncio
async def test_event_committed_during_initial_loading_is_replayed(events: EventStream, checkpoints: EventCheckpointStore) -> None:
    reconciliations: list[int] = []

    async def reconcile() -> None:
        reconciliations.append(len(reconciliations))
        if len(reconciliations) == 1:
            await events.append(MessagingEvent(event_type='connector.discovery.changed', subject='connector'))

    health = RuntimeProjectionHealth()
    synchronizer = _synchronizer(events, checkpoints, reconcile, health)
    await synchronizer.bootstrap()

    assert len(reconciliations) == 2
    assert health.last_applied_sequence == 1
    assert health.ready


@pytest.mark.asyncio
async def test_health_remains_closed_until_bootstrap_event_replay_finishes(checkpoints: EventCheckpointStore) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def read(_sequence: int, _limit: int) -> list[StreamEvent]:
        entered.set()
        await release.wait()
        return []

    events = Mock(spec=EventStream)
    events.list_after.side_effect = read
    health = RuntimeProjectionHealth()
    synchronizer = _synchronizer(events, checkpoints, AsyncMock(), health)
    task = asyncio.create_task(synchronizer.bootstrap())
    await entered.wait()
    assert not health.ready
    release.set()
    await task
    assert health.ready


@pytest.mark.asyncio
@pytest.mark.parametrize('initial_operation', ['bootstrap', 'poll_once'])
async def test_bootstrap_and_polling_serialize_projection_and_checkpoint_publication(events: EventStream, checkpoints: EventCheckpointStore, initial_operation: str) -> None:
    await events.append(MessagingEvent(event_type='connector.discovery.changed', subject='connector'))
    entered = asyncio.Event()
    release = asyncio.Event()
    second_started = asyncio.Event()
    calls: list[int] = []

    async def reconcile() -> None:
        calls.append(len(calls))
        if len(calls) == 1:
            entered.set()
            await release.wait()

    health = RuntimeProjectionHealth()
    synchronizer = _synchronizer(events, checkpoints, reconcile, health)
    first = asyncio.create_task(getattr(synchronizer, initial_operation)())
    await entered.wait()

    async def poll() -> None:
        second_started.set()
        await synchronizer.poll_once()

    second = asyncio.create_task(poll())
    await second_started.wait()
    assert calls == [0]
    release.set()
    await asyncio.gather(first, second)
    assert health.last_applied_sequence == 1
    assert health.ready


@pytest.mark.asyncio
async def test_failed_application_closes_discovery_and_retries_without_checkpoint_advance(events: EventStream, checkpoints: EventCheckpointStore) -> None:
    health = RuntimeProjectionHealth()
    reconcile = AsyncMock()
    synchronizer = _synchronizer(events, checkpoints, reconcile, health)
    await synchronizer.bootstrap()
    await events.append(MessagingEvent(event_type='connector.discovery.changed', subject='connector'))
    reconcile.side_effect = RuntimeError('projection failed')

    with pytest.raises(RuntimeError, match='projection failed'):
        await synchronizer.poll_once()

    assert not health.ready
    assert health.last_applied_sequence == 0
    reconcile.side_effect = None
    await synchronizer.poll_once()
    assert health.ready
    assert health.last_applied_sequence == 1


@pytest.mark.asyncio
async def test_background_consumer_retries_failed_event_and_stops_with_owner(events: EventStream, checkpoints: EventCheckpointStore, caplog: pytest.LogCaptureFixture) -> None:
    await events.append(MessagingEvent(event_type='connector.discovery.changed', subject='connector'))
    health = RuntimeProjectionHealth()
    attempts: list[int] = []

    async def reconcile() -> None:
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise RuntimeError('sensitive payload must not be logged')
        synchronizer.stop()

    synchronizer = RuntimeProjectionSynchronizer(events, checkpoints, reconcile, health, interval_seconds=0.001, batch_limit=100)
    await asyncio.wait_for(synchronizer.run(), timeout=1)
    assert len(attempts) == 2
    assert health.last_applied_sequence == 1
    assert health.ready
    assert 'retrying without advancing checkpoint' in caplog.text
    assert 'sensitive payload' not in caplog.text


@pytest.mark.asyncio
async def test_scoped_routing_uses_snapshot_publication_without_persistence() -> None:
    definition = NoAuthConnectorDefinition(connector_id='connector', display_name='Connector', tool_name_prefix='connector', endpoint_url='https://example.test/mcp', public_path='/mcp/proxies/connector')
    snapshot = DownstreamDiscoverySnapshot(definitions=(definition,), published_connector_ids=frozenset({'connector'}), records=(), namespaces={}, published_records=(), available_records=(), catalogs=(), descriptions={})
    runtime = Mock(spec=DownstreamDiscoveryRuntime)
    runtime.capture.return_value = snapshot

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse({'path': scope['path']})(scope, receive, send)

    health = RuntimeProjectionHealth()
    health.ready = True
    dispatcher = DynamicPublicMcpDispatcher(application, runtime, health)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=dispatcher), base_url='http://test') as client:
        response = await client.get('/mcp/proxies/connector/extra')
        runtime.capture.return_value = DownstreamDiscoverySnapshot(definitions=(definition,), published_connector_ids=frozenset(), records=(), namespaces={}, published_records=(), available_records=(), catalogs=(), descriptions={})
        unpublished = await client.get('/mcp/proxies/connector')

    assert response.json() == {'path': '/mcp/extra'}
    assert unpublished.status_code == 404


@pytest.mark.asyncio
async def test_failed_synchronization_blocks_root_requests() -> None:
    health = RuntimeProjectionHealth()
    application = AsyncMock()
    runtime = Mock(spec=DownstreamDiscoveryRuntime)
    dispatcher = DynamicPublicMcpDispatcher(application, runtime, health)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=dispatcher), base_url='http://test') as client:
        response = await client.get('/mcp')
    assert response.status_code == 503
    application.assert_not_awaited()
    runtime.capture.assert_not_called()


@pytest.mark.asyncio
async def test_restart_rebuilds_and_replays_even_with_prior_worker_checkpoint(events: EventStream, checkpoints: EventCheckpointStore) -> None:
    await events.append(MessagingEvent(event_type='connector.discovery.changed', subject='connector'))
    first_health = RuntimeProjectionHealth()
    await _synchronizer(events, checkpoints, AsyncMock(), first_health).bootstrap()
    restarted_health = RuntimeProjectionHealth()
    restarted_reconcile = AsyncMock()
    await _synchronizer(events, checkpoints, restarted_reconcile, restarted_health).bootstrap()
    assert restarted_reconcile.await_count == 1
    assert restarted_health.last_applied_sequence == 1


@pytest.mark.asyncio
async def test_cancellation_during_apply_does_not_advance_checkpoint(events: EventStream, checkpoints: EventCheckpointStore) -> None:
    await events.append(MessagingEvent(event_type='connector.discovery.changed', subject='connector'))
    health = RuntimeProjectionHealth()
    reconcile = AsyncMock(side_effect=asyncio.CancelledError())
    synchronizer = _synchronizer(events, checkpoints, reconcile, health)
    with pytest.raises(asyncio.CancelledError):
        await synchronizer.poll_once()
    assert health.last_applied_sequence == 0
    reconcile.side_effect = None
    await synchronizer.poll_once()
    assert health.last_applied_sequence == 1


@pytest.mark.asyncio
async def test_sql_bootstrap_without_api_url_never_copies_authoritative_store_state(monkeypatch: pytest.MonkeyPatch, events: EventStream, checkpoints: EventCheckpointStore) -> None:
    configuration = Mock()
    publishing = Mock()
    coordinator = SimpleNamespace(reconcile_native_capabilities=AsyncMock())
    from umbod.mcp.connectors.downstream_mcp.capability_notifications import CapabilityListChangeNotifier

    registry = SimpleNamespace(reconcile_all=AsyncMock(), client_notifier=Mock(spec=CapabilityListChangeNotifier))
    context = SimpleNamespace(
        api_base_url=None,
        source_strategy=StoreBackedConnectorRuntimeStateSourceStrategy(),
        settings=SimpleNamespace(mcp=SimpleNamespace(messaging_transport='sql')),
        persistence_runtime=SimpleNamespace(database=object()),
        group_permission_runtime_state=None,
        connector_runtime=SimpleNamespace(connector_tool_mappings=[], connector_configuration_store=configuration, connector_publishing_store=publishing),
        mcp=SimpleNamespace(runtime_projection_health=RuntimeProjectionHealth(), downstream_mcp_discovery_coordinator=coordinator, connector_tool_registry=registry, connector_prompt_registry=SimpleNamespace(reconcile_all=AsyncMock()), connector_resource_registry=SimpleNamespace(reconcile_all=AsyncMock())),
    )
    adapters = SimpleNamespace(create_projection_reader=lambda: events, create_checkpoint_store=lambda: checkpoints)
    monkeypatch.setattr(public_app, 'McpMessagingAdapterFactory', lambda *_args: adapters)
    monkeypatch.setattr(public_app, 'reconcile_openapi_discovery', AsyncMock())
    synchronizer = await public_app._initialize_runtime_projection(context)
    assert isinstance(synchronizer, RuntimeProjectionSynchronizer)
    assert context.mcp.runtime_projection_health.ready
    coordinator.reconcile_native_capabilities.assert_awaited_once()
    registry.reconcile_all.assert_awaited_once()
    assert configuration.mock_calls == []
    assert publishing.mock_calls == []
