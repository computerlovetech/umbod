from typing import Literal

import pytest

from umbod.mcp.connectors.native.tools import (
    ConnectorToolRuntimeStateSynchronizer,
    RuntimeReconciliationResult,
)
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.core.activation.events import connector_capability_activation_changed_event
from messaging.ports import EventStream
from tests.support.messaging import (
    InMemoryEventStreamFactory,
)


ConnectorToolStatus = Literal["enabled", "disabled"]


def make_tool_change_stream() -> EventStream:
    return InMemoryEventStreamFactory("Connector tool change event stream is closed").create()


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


@pytest.mark.asyncio
async def test_api_publishes_metadata_only_tool_changed_event() -> None:
    stream = make_tool_change_stream()
    event = await stream.append(
        connector_capability_activation_changed_event("native", "test", "tool", "echo")
    )

    assert event.sequence == 1
    assert event.event.metadata == {
        "connector_kind": "native", "connector_id": "test",
        "capability_kind": "tool", "capability_key": "echo",
    }


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
