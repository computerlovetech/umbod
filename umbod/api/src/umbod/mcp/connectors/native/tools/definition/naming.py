from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.core.capabilities.tools.names import mangle_public_tool_name


def _tool_name(mapping: ConnectorToolMapping) -> str:
    return _mangle_tool_name(
        getattr(mapping, "tool_name_prefix", "") or mapping.connector_id,
        mapping.operation_name,
    )


def _mangle_tool_name(tool_name_prefix: str, operation_name: str) -> str:
    return mangle_public_tool_name(tool_name_prefix, operation_name)
