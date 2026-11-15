import json
from typing import Any

from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr

from umbod.core.filesystem.browsing.exploration import BrowsingExplorer, ListingLimits, TreeLimits
from umbod.mcp.responses.progress import operation_completed

from .argument_errors import argument_json
from .browsing_models import (
    BROWSE_COMMAND,
    BROWSE_RESPONSE,
    DirectoryListingResponse,
    DirectoryTreeResponse,
    FilesystemDirectoryListing,
    FilesystemDirectoryTree,
    FilesystemNodeInspection,
    FilesystemTreeEntry,
    InspectNode,
    ListNamespaces,
    NamespaceListing,
    NamespaceListingResponse,
    ResolveHome,
    HomeResponse,
    NodeInspectionResponse,
    ReadTree,
    browse_input_schema,
)
from .browsing_scope import PersonalNamespaceTargets
from .errors import filesystem_operation
from .links import file_link_result
from .ports import FilesystemCallerCapture, FilesystemServiceFactory
from .rendering import render_inspection, render_listing, render_tree
from .sharing import enrich_nodes


class FilesystemBrowseTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_browse",
            description=(
                "Browse the remote Umbod filesystem, not the server host. "
                "For an upload it to Umbod request, use targetless operation home to resolve the safe default. "
                "Home idempotently provisions your private home; use returned node.id as upload parent. "
                "Inspect permissions.can_write and visible_to, begin an original-byte upload, transfer and complete it, "
                "then report the receipt and visibility. Never invent paths, UUIDs or hashes. "
                "Use targetless operation namespaces to list your personal namespace and accessible shared namespaces. "
                "Shared namespace access applies to every descendant; uploads there are not private to the creator. "
                "Declare ls for immediate entries, tree for a bounded recursive overview, "
                "or stat for node details. Target root or an absolute path within your personal namespace, "
                "or use a returned namespace root_node_id as a node UUID to browse shared files. "
                "No working directory or shell execution. Only discoverable nodes are returned; "
                "breadcrumbs may be partial. Limits bound returned entries, not storage work. "
                "Separate reads may observe concurrent changes. No file bytes are read. "
                f"File entries include MCP resource links; use resources/read to read their current content (maximum {services.read_max_bytes()} bytes). "
                "view_url opens the authenticated Umbod browser view, not a public share, download, or MCP resource read. "
                "Visibility identifies the containing namespace, not the complete audience. "
                "Sharing metadata describes manageable direct group and user grants; inherited folder shares also apply."
            ),
            parameters=browse_input_schema(),
            output_schema={"type": "object", **BROWSE_RESPONSE.json_schema()},
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False,
            ),
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        command = BROWSE_COMMAND.validate_json(argument_json(arguments, allow_nan=True))
        with filesystem_operation():
            caller = self._callers.capture()
            if isinstance(command, ListNamespaces):
                namespaces = await self._services.namespaces().list(caller)
                operation_completed()
                listing = NamespaceListing(namespaces=namespaces)
                response = NamespaceListingResponse(operation="namespaces", result=listing)
                rendered = "\n".join(
                    f"{json.dumps(namespace.name, ensure_ascii=True)} ({namespace.kind}): "
                    f"root_node_id={namespace.root_node_id}; "
                    f"description={json.dumps(namespace.description, ensure_ascii=False)}; "
                    f"permissions={','.join(sorted(permission.value for permission in namespace.permissions))}"
                    for namespace in namespaces
                )
                return file_link_result(response, [], rendered, self._services.read_max_bytes())
            browsing = self._services.browsing()
            explorer = BrowsingExplorer(browsing)
            targets = PersonalNamespaceTargets(browsing, self._services.homes())
            if isinstance(command, ResolveHome):
                node = await self._services.homes().get_or_provision(caller)
                operation_completed()
                nodes = await enrich_nodes(self._services.sharing(), caller, [node], self._services.access(), self._services.view_url)
                breadcrumbs = await self._services.browsing().get_breadcrumbs(caller, node.id)
                inspection = FilesystemNodeInspection(node=nodes[0], breadcrumbs=breadcrumbs)
                response = HomeResponse(operation="home", result=inspection)
                rendered = render_inspection(inspection)
            elif isinstance(command, InspectNode):
                inspection = await explorer.inspect_node(caller, await targets.resolve(caller, command.target))
                operation_completed()
                nodes = await enrich_nodes(self._services.sharing(), caller, [inspection.node], self._services.access(), self._services.view_url)
                inspection = FilesystemNodeInspection(node=nodes[0], breadcrumbs=inspection.breadcrumbs)
                response = NodeInspectionResponse(operation="stat", result=inspection)
                rendered = render_inspection(inspection)
            elif isinstance(command, ReadTree):
                tree = await explorer.read_tree(
                    caller, await targets.resolve(caller, command.target),
                    TreeLimits(depth=command.depth, max_entries=command.max_entries),
                )
                operation_completed()
                nodes = await enrich_nodes(
                    self._services.sharing(), caller, [tree.node, *(entry.node for entry in tree.entries)], self._services.access(), self._services.view_url,
                )
                tree = FilesystemDirectoryTree(
                    node=nodes[0], breadcrumbs=tree.breadcrumbs, expansion=tree.expansion,
                    entries=[FilesystemTreeEntry(
                        node=node, depth=entry.depth, expansion=entry.expansion,
                    ) for entry, node in zip(tree.entries, nodes[1:], strict=True)],
                )
                response = DirectoryTreeResponse(operation="tree", result=tree)
                rendered = render_tree(tree)
            else:
                listing = await explorer.list_directory(
                    caller, await targets.resolve(caller, command.target), ListingLimits(max_entries=command.max_entries),
                )
                operation_completed()
                nodes = await enrich_nodes(
                    self._services.sharing(), caller, [listing.node, *listing.entries], self._services.access(), self._services.view_url,
                )
                listing = FilesystemDirectoryListing(
                    node=nodes[0], breadcrumbs=listing.breadcrumbs,
                    entries=nodes[1:], truncated=listing.truncated,
                )
                response = DirectoryListingResponse(operation="ls", result=listing)
                rendered = render_listing(listing)
            return file_link_result(response, nodes, rendered, self._services.read_max_bytes())
