import json

from umbod.core.filesystem.browsing import Breadcrumbs
from umbod.core.filesystem.models import NodeKind

from .browsing_models import (
    FilesystemDirectoryListing, FilesystemDirectoryTree, FilesystemNodeInspection,
)
from .models import AuthorizedSharingMetadata, FilesystemNodeSummary


def visible_location(breadcrumbs: Breadcrumbs) -> str:
    prefix = "/" if breadcrumbs.complete else ".../"
    return prefix + "/".join(item.name for item in breadcrumbs.items if item.name)


def sharing_label(node: FilesystemNodeSummary) -> str:
    if not isinstance(node.sharing, AuthorizedSharingMetadata):
        return "sharing unavailable (not permitted)"
    if not node.sharing.grants:
        return "no manageable direct grants"
    return "manageable direct sharing=" + json.dumps(
        [grant.model_dump(mode="json") for grant in node.sharing.grants], ensure_ascii=False,
    )


def node_label(node: FilesystemNodeSummary) -> str:
    suffix = "/" if node.kind == NodeKind.DIRECTORY else ""
    return f"{json.dumps(node.name, ensure_ascii=False)}{suffix} [{node.id}] {sharing_label(node)}"


def render_inspection(result: FilesystemNodeInspection) -> str:
    node = result.node
    return "\n".join((
        json.dumps(visible_location(result.breadcrumbs), ensure_ascii=False),
        f"{node.kind.value} [{node.id}] revision={node.revision}",
        f"created={node.created_at.isoformat()} updated={node.updated_at.isoformat()}",
        f"metadata={node.metadata.model_dump_json()}",
        sharing_label(node),
    ))


def render_listing(result: FilesystemDirectoryListing) -> str:
    lines = [json.dumps(visible_location(result.breadcrumbs), ensure_ascii=False), node_label(result.node)]
    lines.extend(node_label(node) for node in result.entries)
    if result.truncated:
        lines.append("[entry limit reached; listing incomplete]")
    elif not result.entries:
        lines.append("[no visible entries]")
    return "\n".join(lines)


def render_tree(result: FilesystemDirectoryTree) -> str:
    lines = [json.dumps(visible_location(result.breadcrumbs), ensure_ascii=False), node_label(result.node)]
    for entry in result.entries:
        suffix = f" [{entry.expansion}]" if entry.expansion in ("depth_limit", "entry_limit") else ""
        lines.append(f"{'  ' * entry.depth}{node_label(entry.node)}{suffix}")
    if result.expansion == "entry_limit":
        lines.append("[entry limit reached; tree incomplete]")
    elif not result.entries:
        lines.append("[no visible entries]")
    return "\n".join(lines)
