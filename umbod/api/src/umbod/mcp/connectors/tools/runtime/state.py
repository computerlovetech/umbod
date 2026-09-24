from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState


class InMemoryConnectorToolRuntimeStateStore:
    def __init__(self) -> None:
        self._states: dict[ConnectorToolRef, ConnectorToolRuntimeState] = {}

    def get_runtime_state(self, key: ConnectorToolRef) -> ConnectorToolRuntimeState | None:
        return self._states.get(key)

    def save_runtime_state(self, state: ConnectorToolRuntimeState) -> None:
        self._states[state.key] = state

    def delete_runtime_state(self, key: ConnectorToolRef) -> None:
        self._states.pop(key, None)
