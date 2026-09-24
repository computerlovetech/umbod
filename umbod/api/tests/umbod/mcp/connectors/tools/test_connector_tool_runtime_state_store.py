from umbod.mcp.connectors.tools import InMemoryConnectorToolRuntimeStateStore
from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState


def test_get_runtime_state_returns_none_for_missing_key() -> None:
    store = InMemoryConnectorToolRuntimeStateStore()

    state = store.get_runtime_state(
        ConnectorToolRef(connector_id="slack", operation_name="send_message")
    )

    assert state is None


def test_save_runtime_state_roundtrips_by_key() -> None:
    store = InMemoryConnectorToolRuntimeStateStore()
    key = ConnectorToolRef(connector_id="slack", operation_name="send_message")
    runtime_state = ConnectorToolRuntimeState(key=key, status="enabled")

    store.save_runtime_state(runtime_state)

    assert store.get_runtime_state(key) == runtime_state


def test_save_runtime_state_replaces_existing_state_for_key() -> None:
    store = InMemoryConnectorToolRuntimeStateStore()
    key = ConnectorToolRef(connector_id="slack", operation_name="send_message")
    store.save_runtime_state(ConnectorToolRuntimeState(key=key, status="enabled"))
    replacement_state = ConnectorToolRuntimeState(key=key, status="disabled")

    store.save_runtime_state(replacement_state)

    assert store.get_runtime_state(key) == replacement_state


def test_delete_runtime_state_removes_saved_state() -> None:
    store = InMemoryConnectorToolRuntimeStateStore()
    key = ConnectorToolRef(connector_id="slack", operation_name="send_message")
    store.save_runtime_state(ConnectorToolRuntimeState(key=key, status="enabled"))

    store.delete_runtime_state(key)

    assert store.get_runtime_state(key) is None


def test_delete_runtime_state_ignores_missing_key() -> None:
    store = InMemoryConnectorToolRuntimeStateStore()
    key = ConnectorToolRef(connector_id="slack", operation_name="send_message")

    store.delete_runtime_state(key)

    assert store.get_runtime_state(key) is None
