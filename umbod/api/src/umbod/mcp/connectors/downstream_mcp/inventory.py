from umbod.core.capabilities.tools.names import mangle_public_tool_name
from collections.abc import Sequence

from umbod.core.connectors.downstream_mcp.catalog import DownstreamCapabilityRecord
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.mcp.signals import McpToolIdentity, ToolInventoryObserved


def shared_tool_inventory(records: Sequence[DownstreamCapabilityRecord]) -> ToolInventoryObserved:
    identities: list[McpToolIdentity] = []
    for record in records:
        if uses_personal_oauth(record.definition) or record.capability.identity.capability_kind != "tool" or record.source_tool is None:
            continue
        definition = record.definition
        backend_name = record.source_tool.identity.downstream_name
        public_names = (mangle_public_tool_name(definition.tool_name_prefix, backend_name), backend_name)
        identities.extend(McpToolIdentity(tool_name=name, connector_id=definition.connector_id, operation_name=backend_name, connector_name=definition.display_name) for name in dict.fromkeys(public_names))
    return ToolInventoryObserved(tuple(identities))
