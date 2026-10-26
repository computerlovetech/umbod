from umbod.core.connectors.openapi.stores import OpenApiConnectorReader
from umbod.mcp.signals.events import McpToolIdentity, ToolInventoryObserved


async def read_openapi_tool_inventory(reader: OpenApiConnectorReader) -> ToolInventoryObserved:
    return ToolInventoryObserved(
        identities=tuple(
            McpToolIdentity(
                tool_name="execute_openapi",
                connector_id=connector.connector_id,
                connector_name=connector.display_name,
                operation_name=None,
            )
            for connector in await reader.list_connectors()
        )
    )
