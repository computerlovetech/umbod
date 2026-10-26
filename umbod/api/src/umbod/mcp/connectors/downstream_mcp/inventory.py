from umbod.core.capabilities.tools.names import mangle_public_tool_name
from umbod.core.connectors.downstream_mcp.catalog import StoreBackedDownstreamCapabilityCatalog
from umbod.core.connectors.downstream_mcp.models import uses_personal_oauth
from umbod.core.connectors.downstream_mcp.stores import ConnectorDefinitionStore, ToolCatalogStore
from umbod.mcp.signals import McpToolIdentity, ToolInventoryObserved


async def read_shared_tool_inventory(definitions: ConnectorDefinitionStore, catalogs: ToolCatalogStore) -> ToolInventoryObserved:
    identities: list[McpToolIdentity] = []
    for record in await StoreBackedDownstreamCapabilityCatalog(definitions, catalogs).list_records():
        if uses_personal_oauth(record.definition) or record.capability.identity.capability_kind != "tool" or record.source_tool is None:
            continue
        definition = record.definition
        backend_name = record.source_tool.identity.downstream_name
        public_names = (mangle_public_tool_name(definition.tool_name_prefix, backend_name), backend_name)
        identities.extend(McpToolIdentity(tool_name=name, connector_id=definition.connector_id, operation_name=backend_name, connector_name=definition.display_name) for name in dict.fromkeys(public_names))
    return ToolInventoryObserved(tuple(identities))
