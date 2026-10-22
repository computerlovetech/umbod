from mcp.types import Tool

from ..models import DiscoveredTool, DiscoveredToolWithOutputSchema, DiscoveredToolWithoutOutputSchema, ToolIdentity
from ..probe import DiscoveredCapabilityTool


def map_sdk_tool(tool: Tool) -> DiscoveredCapabilityTool:
    return DiscoveredCapabilityTool(
        name=tool.name,
        title=tool.title or tool.name,
        description=tool.description or "",
        input_schema=tool.input_schema,
        output_schema=tool.output_schema,
        annotations=tool.annotations.model_dump(mode="json", by_alias=True, exclude_none=True) if tool.annotations is not None else {},
        icons=tuple(icon.model_dump(mode="json", by_alias=True, exclude_none=True) for icon in tool.icons or ()),
        meta=tool.meta or {},
        execution=tool.execution.model_dump(mode="json", by_alias=True, exclude_none=True) if tool.execution is not None else {},
    )


def bind_tool(connector_id: str, tool: DiscoveredCapabilityTool) -> DiscoveredTool:
    shared = tool.model_dump(exclude={"name", "output_schema"})
    shared["identity"] = ToolIdentity(connector_id=connector_id, downstream_name=tool.name)
    if tool.output_schema is None:
        return DiscoveredToolWithoutOutputSchema(**shared)
    return DiscoveredToolWithOutputSchema(**shared, output_schema=tool.output_schema)
