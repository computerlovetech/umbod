from typing import Any

from fastmcp.utilities.components import get_fastmcp_metadata
from mcp.types import Tool as McpTool

from umbod.core.connectors.downstream_mcp.models import DiscoveredTool


def tool_descriptor_options(catalog: DiscoveredTool) -> dict[str, Any]:
    descriptor = McpTool(
        name=catalog.identity.downstream_name,
        title=catalog.title,
        description=catalog.description,
        inputSchema=catalog.input_schema,
        outputSchema=catalog.output_schema if catalog.output_schema_status == "present" else None,
        annotations=catalog.annotations or None,
        icons=list(catalog.icons),
        _meta=catalog.meta or None,
        execution=catalog.execution or None,
    )
    return {
        "title": descriptor.title,
        "description": descriptor.description,
        "parameters": descriptor.input_schema,
        "output_schema": descriptor.output_schema,
        "annotations": descriptor.annotations,
        "icons": descriptor.icons,
        "meta": descriptor.meta,
        "tags": get_fastmcp_metadata(descriptor.meta).get("tags", []),
        "execution": descriptor.execution,
    }
