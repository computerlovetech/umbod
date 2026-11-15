from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

from fastmcp.tools.base import ToolResult
from mcp.types import ResourceLink, TextContent
from pydantic import BaseModel

from umbod.config.app import validate_site_origin
from umbod.core.filesystem.access import CallerNodeSummary
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.models import NodeKind

from .models import FilesystemViewNodeSummary


FILE_RESOURCE_TEMPLATE = "umbod://filesystem/files/{node_id}"


@dataclass(frozen=True)
class FilesystemViewUrls:
    site_base_url: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "site_base_url", validate_site_origin(self.site_base_url))

    def for_node(self, node_id: UUID) -> str:
        return f"{self.site_base_url}/files?node={node_id}"


def project_view_node(node: CallerNodeSummary, view_url: Callable[[UUID], str]) -> FilesystemViewNodeSummary:
    return FilesystemViewNodeSummary(
        **node.model_dump(), view_url=view_url(node.id) if node.permissions.can_discover else None,
    )


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
