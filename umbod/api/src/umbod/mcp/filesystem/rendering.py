import json

from umbod.core.filesystem.browsing import Breadcrumbs, NodeSummary
from umbod.core.filesystem.browsing.exploration import DirectoryListing, DirectoryTree, NodeInspection
from umbod.core.filesystem.models import NodeKind


def visible_location(breadcrumbs: Breadcrumbs) -> str:
    prefix = "/" if breadcrumbs.complete else ".../"
    return prefix + "/".join(item.name for item in breadcrumbs.items if item.name)


def node_label(node: NodeSummary) -> str:
    suffix = "/" if node.kind == NodeKind.DIRECTORY else ""
    return f"{json.dumps(node.name, ensure_ascii=False)}{suffix} [{node.id}]"


def render_inspection(result: NodeInspection) -> str:
    node = result.node
    return "\n".join((
        json.dumps(visible_location(result.breadcrumbs), ensure_ascii=False),
        f"{node.kind.value} [{node.id}] revision={node.revision}",
        f"created={node.created_at.isoformat()} updated={node.updated_at.isoformat()}",
        f"metadata={node.metadata.model_dump_json()}",
    ))


def render_listing(result: DirectoryListing) -> str:
    lines = [json.dumps(visible_location(result.breadcrumbs), ensure_ascii=False)]
    lines.extend(node_label(node) for node in result.entries)
    if result.truncated:
        lines.append("[entry limit reached; listing incomplete]")
    elif not result.entries:
        lines.append("[no visible entries]")
    return "\n".join(lines)


def render_tree(result: DirectoryTree) -> str:
    lines = [json.dumps(visible_location(result.breadcrumbs), ensure_ascii=False)]
    for entry in result.entries:
        suffix = f" [{entry.expansion}]" if entry.expansion in ("depth_limit", "entry_limit") else ""
        lines.append(f"{'  ' * entry.depth}{node_label(entry.node)}{suffix}")
    if result.expansion == "entry_limit":
        lines.append("[entry limit reached; tree incomplete]")
    elif not result.entries:
        lines.append("[no visible entries]")
    return "\n".join(lines)
