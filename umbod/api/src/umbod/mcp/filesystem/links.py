from collections.abc import Sequence
from uuid import UUID

from fastmcp.tools.base import ToolResult
from mcp.types import ResourceLink, TextContent
from pydantic import BaseModel

from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.models import NodeKind


FILE_RESOURCE_TEMPLATE = "umbod://filesystem/files/{node_id}"


def file_resource_uri(node_id: UUID) -> str:
    return FILE_RESOURCE_TEMPLATE.format(node_id=node_id)


def file_links(nodes: Sequence[NodeSummary], max_read_bytes: int) -> list[ResourceLink]:
    links: list[ResourceLink] = []
    seen: set[UUID] = set()
    for node in nodes:
        if node.kind != NodeKind.FILE or node.id in seen:
            continue
        seen.add(node.id)
        content_type = node.metadata.content_type
        links.append(ResourceLink(
            type="resource_link", uri=file_resource_uri(node.id), name=node.name,
            mimeType=content_type if isinstance(content_type, str) else "application/octet-stream",
            description=f"Current file content. Reading requires current discover and read permissions; maximum {max_read_bytes} bytes.",
            annotations={"lastModified": node.updated_at.isoformat()},
        ))
    return links


def file_link_result(result: BaseModel, nodes: Sequence[NodeSummary], rendered: str, max_read_bytes: int) -> ToolResult:
    return ToolResult(
        content=[TextContent(type="text", text=rendered), *file_links(nodes, max_read_bytes)],
        structured_content=result.model_dump(mode="json"),
    )
