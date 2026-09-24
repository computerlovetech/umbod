from tests.connector_event_adapters import (
    ConnectorEventCheckpointStoreAdapter,
    ConnectorToolChangeEventStreamAdapter,
)
from typing import Literal

import pytest

from umbod.mcp.connectors.tools import (
    ConnectorToolChangePollingSynchronizer,
    ConnectorToolRuntimeStateSynchronizer,
    RuntimeReconciliationResult,
)
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.core.activation.events import ConnectorToolChanged, ConnectorToolChangedStreamEvent
from messaging.in_memory import (
    InMemoryEventCheckpointStoreFactory,
    InMemoryEventCheckpointStoreMessages,
    InMemoryEventStreamFactory,
)


ConnectorToolStatus = Literal["enabled", "disabled"]


def make_tool_change_stream() -> ConnectorToolChangeEventStreamAdapter:
    return ConnectorToolChangeEventStreamAdapter(
        InMemoryEventStreamFactory("Connector tool change event stream is closed").create()
    )


def make_tool_change_checkpoint_store() -> ConnectorEventCheckpointStoreAdapter:
    return ConnectorEventCheckpointStoreAdapter(
        InMemoryEventCheckpointStoreFactory(
            InMemoryEventCheckpointStoreMessages(
                closed_error_message="Connector tool change event checkpoint store is closed",
                lower_sequence_error_message="Cannot save a lower connector tool change checkpoint sequence",
            )
        ).create()
    )


class RecordingRuntimeStateReader:
    def __init__(
        self,
        states: dict[ConnectorToolRef, ConnectorToolRuntimeState | None],
        requested_keys: list[ConnectorToolRef],
        fail: bool,
    ) -> None:
        self.states = states
        self.requested_keys = requested_keys
        self.fail = fail

    async def get_runtime_state(self, key: ConnectorToolRef) -> ConnectorToolRuntimeState | None:
        self.requested_keys.append(key)
        if self.fail:
            raise RuntimeError("tool state lookup unavailable")
        return self.states.get(key)


class RecordingRuntimeStateStore:
    def __init__(
        self, saved_states: list[ConnectorToolRuntimeState], deleted_keys: list[ConnectorToolRef]
    ) -> None:
        self.saved_states = saved_states
        self.deleted_keys = deleted_keys

    def save_runtime_state(self, state: ConnectorToolRuntimeState) -> None:
        self.saved_states.append(state)

    def delete_runtime_state(self, key: ConnectorToolRef) -> None:
        self.deleted_keys.append(key)


class RecordingRuntimeStateReconciler:
    def __init__(
        self, reconciled_keys: list[ConnectorToolRef], result: RuntimeReconciliationResult
    ) -> None:
        self.reconciled_keys = reconciled_keys
        self.result = result

    async def reconcile_runtime_state(self, key: ConnectorToolRef) -> RuntimeReconciliationResult:
        self.reconciled_keys.append(key)
        return self.result


class RecordingConnectorToolChangeStreamReader:
    def __init__(self, events: list[ConnectorToolChangedStreamEvent]) -> None:
        self.events = events
        self.requests: list[tuple[int, int]] = []

    async def list_after(self, sequence: int, limit: int) -> list[ConnectorToolChangedStreamEvent]:
        self.requests.append((sequence, limit))
        return [event for event in self.events if event.sequence > sequence][:limit]


def create_reconciler(
    resource_name: str,
    visible_before: bool,
    visible_after: bool,
    clients_notified: bool,
) -> RecordingRuntimeStateReconciler:
    return RecordingRuntimeStateReconciler(
        reconciled_keys=[],
        result=RuntimeReconciliationResult(
            resource_name=resource_name,
            visible_before=visible_before,
            visible_after=visible_after,
            clients_notified=clients_notified,
        ),
    )


def create_single_event_stream_reader(
    sequence: int,
    connector_id: str,
    operation_name: str,
) -> RecordingConnectorToolChangeStreamReader:
    return RecordingConnectorToolChangeStreamReader(
        [
            ConnectorToolChangedStreamEvent(
                sequence=sequence,
                event=ConnectorToolChanged(connector_kind="native", connector_id=connector_id, capability_kind="tool", capability_key=operation_name
                ),
            )
        ]
    )


@pytest.mark.asyncio
async def test_api_publishes_metadata_only_tool_changed_event() -> None:
    stream = make_tool_change_stream()
    tool = ConnectorToolRef(connector_id="test", operation_name="echo")

    event = await stream.append_connector_tool_changed(
        ConnectorToolChanged(connector_kind="native", connector_id="test", capability_kind="tool", capability_key="echo")
    )

    assert event.sequence == 1
    assert event.event.key == tool
    assert not hasattr(event.event, "status")
    assert not hasattr(event.event, "activation_status")


@pytest.mark.asyncio
async def test_sync_tool_fetches_current_state_saves_it_and_reconciles_only_changed_tool() -> None:
    tool = ConnectorToolRef(connector_id="test", operation_name="echo")
    sibling_tool = ConnectorToolRef(connector_id="test", operation_name="get_default_response")
    state = ConnectorToolRuntimeState(key=tool, status="enabled")
    reader = RecordingRuntimeStateReader(states={tool: state}, requested_keys=[], fail=False)
    store = RecordingRuntimeStateStore(saved_states=[], deleted_keys=[])
    reconciler = RecordingRuntimeStateReconciler(
        reconciled_keys=[],
        result=RuntimeReconciliationResult(
            resource_name="test_echo",
            visible_before=False,
            visible_after=True,
            clients_notified=True,
        ),
    )
    synchronizer = ConnectorToolRuntimeStateSynchronizer(
        reader=reader, store=store, reconciler=reconciler
    )

    result = await synchronizer.sync_runtime_state(tool)

    assert reader.requested_keys == [tool]
    assert store.saved_states == [state]
    assert store.deleted_keys == []
    assert reconciler.reconciled_keys == [tool]
    assert sibling_tool not in reconciler.reconciled_keys
    assert result.visible_after is True
    assert result.clients_notified is True


@pytest.mark.asyncio
async def test_sync_tool_deletes_stale_runtime_state_when_current_state_is_missing() -> None:
    tool = ConnectorToolRef(connector_id="github", operation_name="search_issues")
    reader = RecordingRuntimeStateReader(states={tool: None}, requested_keys=[], fail=False)
    store = RecordingRuntimeStateStore(saved_states=[], deleted_keys=[])
    reconciler = RecordingRuntimeStateReconciler(
        reconciled_keys=[],
        result=RuntimeReconciliationResult(
            resource_name="github_search_issues",
            visible_before=True,
            visible_after=False,
            clients_notified=True,
        ),
    )
    synchronizer = ConnectorToolRuntimeStateSynchronizer(
        reader=reader, store=store, reconciler=reconciler
    )

    result = await synchronizer.sync_runtime_state(tool)

    assert reader.requested_keys == [tool]
    assert store.saved_states == []
    assert store.deleted_keys == [tool]
    assert reconciler.reconciled_keys == [tool]
    assert result.visible_after is False
    assert result.clients_notified is True


@pytest.mark.asyncio
async def test_polling_tool_change_event_updates_runtime_state_then_checkpoints() -> None:
    tool = ConnectorToolRef(connector_id="slack", operation_name="read_messages")
    state = ConnectorToolRuntimeState(key=tool, status="enabled")
    reader = RecordingRuntimeStateReader(states={tool: state}, requested_keys=[], fail=False)
    store = RecordingRuntimeStateStore(saved_states=[], deleted_keys=[])
    reconciler = create_reconciler(
        resource_name="slack_read_messages",
        visible_before=False,
        visible_after=True,
        clients_notified=True,
    )
    runtime_synchronizer = ConnectorToolRuntimeStateSynchronizer(
        reader=reader, store=store, reconciler=reconciler
    )
    checkpoint_store = make_tool_change_checkpoint_store()
    stream_reader = create_single_event_stream_reader(
        sequence=3, connector_id="slack", operation_name="read_messages"
    )
    polling_synchronizer = ConnectorToolChangePollingSynchronizer(
        consumer_id="consumer",
        checkpoint_store=checkpoint_store,
        stream_reader=stream_reader,
        handler=lambda event: runtime_synchronizer.sync_runtime_state(event.key),
    )

    await polling_synchronizer.poll_once()

    assert reader.requested_keys == [tool]
    assert store.saved_states == [state]
    assert reconciler.reconciled_keys == [tool]
    assert await checkpoint_store.get_last_processed_sequence("consumer") == 3


@pytest.mark.asyncio
async def test_polling_tool_change_event_does_not_checkpoint_when_state_lookup_fails() -> None:
    reader = RecordingRuntimeStateReader(states={}, requested_keys=[], fail=True)
    store = RecordingRuntimeStateStore(saved_states=[], deleted_keys=[])
    reconciler = create_reconciler(
        resource_name="test_echo",
        visible_before=False,
        visible_after=False,
        clients_notified=False,
    )
    runtime_synchronizer = ConnectorToolRuntimeStateSynchronizer(
        reader=reader, store=store, reconciler=reconciler
    )
    checkpoint_store = make_tool_change_checkpoint_store()
    stream_reader = create_single_event_stream_reader(
        sequence=4, connector_id="test", operation_name="echo"
    )
    polling_synchronizer = ConnectorToolChangePollingSynchronizer(
        consumer_id="consumer",
        checkpoint_store=checkpoint_store,
        stream_reader=stream_reader,
        handler=lambda event: runtime_synchronizer.sync_runtime_state(event.key),
    )

    with pytest.raises(RuntimeError, match="tool state lookup unavailable"):
        await polling_synchronizer.poll_once()

    assert store.saved_states == []
    assert store.deleted_keys == []
    assert reconciler.reconciled_keys == []
    assert await checkpoint_store.get_last_processed_sequence("consumer") == 0



@pytest.mark.asyncio
async def test_polling_prompt_activation_event_does_not_sync_tool_runtime() -> None:
    tool_calls: list[ConnectorToolRef] = []
    prompt_calls: list[str] = []

    async def handle(event: ConnectorToolChanged) -> None:
        if event.capability_kind == "tool":
            tool_calls.append(event.key)
            return
        if event.capability_kind == "prompt":
            prompt_calls.append(event.connector_id)

    checkpoint_store = make_tool_change_checkpoint_store()
    stream_reader = RecordingConnectorToolChangeStreamReader(
        [
            ConnectorToolChangedStreamEvent(
                sequence=5,
                event=ConnectorToolChanged(
                    connector_kind="native",
                    connector_id="weather",
                    capability_kind="prompt",
                    capability_key="forecast",
                ),
            )
        ]
    )
    polling_synchronizer = ConnectorToolChangePollingSynchronizer(
        consumer_id="consumer",
        checkpoint_store=checkpoint_store,
        stream_reader=stream_reader,
        handler=handle,
    )

    await polling_synchronizer.poll_once()

    assert tool_calls == []
    assert prompt_calls == ["weather"]
    assert await checkpoint_store.get_last_processed_sequence("consumer") == 5


@pytest.mark.asyncio
async def test_polling_tool_activation_event_still_syncs_tool_runtime() -> None:
    tool = ConnectorToolRef(connector_id="slack", operation_name="read_messages")
    state = ConnectorToolRuntimeState(key=tool, status="enabled")
    reader = RecordingRuntimeStateReader(states={tool: state}, requested_keys=[], fail=False)
    store = RecordingRuntimeStateStore(saved_states=[], deleted_keys=[])
    reconciler = create_reconciler(
        resource_name="slack_read_messages",
        visible_before=False,
        visible_after=True,
        clients_notified=True,
    )
    runtime_synchronizer = ConnectorToolRuntimeStateSynchronizer(
        reader=reader, store=store, reconciler=reconciler
    )

    async def handle(event: ConnectorToolChanged) -> None:
        if event.capability_kind == "tool":
            await runtime_synchronizer.sync_runtime_state(event.key)

    checkpoint_store = make_tool_change_checkpoint_store()
    stream_reader = create_single_event_stream_reader(
        sequence=6, connector_id="slack", operation_name="read_messages"
    )
    polling_synchronizer = ConnectorToolChangePollingSynchronizer(
        consumer_id="consumer",
        checkpoint_store=checkpoint_store,
        stream_reader=stream_reader,
        handler=handle,
    )

    await polling_synchronizer.poll_once()

    assert reader.requested_keys == [tool]
    assert store.saved_states == [state]
    assert reconciler.reconciled_keys == [tool]
