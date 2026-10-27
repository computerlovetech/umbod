from umbod.core.capabilities.tools.refs import ConnectorToolRef
from umbod.core.connectors.native.tools.runtime_state import ConnectorToolRuntimeState
from umbod.mcp.connectors.native.tools.runtime.state import InMemoryConnectorToolRuntimeStateStore


def enabled_native_tool_states(
    *identities: tuple[str, str],
) -> InMemoryConnectorToolRuntimeStateStore:
    states = InMemoryConnectorToolRuntimeStateStore()
    for connector_id, operation_name in identities:
        states.save_runtime_state(ConnectorToolRuntimeState(
            key=ConnectorToolRef(connector_id, operation_name), status="enabled",
        ))
    return states
