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
    ResolveHome,
    HomeResponse,
    NodeInspectionResponse,
    ReadTree,
    browse_input_schema,
)
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
                "Declare ls for immediate entries, tree for a bounded recursive overview, "
                "or stat for node details. Target root, an absolute path, or a node UUID. "
                "No working directory or shell execution. Only discoverable nodes are returned; "
                "breadcrumbs may be partial. Limits bound returned entries, not storage work. "
                "Separate reads may observe concurrent changes. No file bytes are read. "
                "File entries include MCP resource links; use resources/read to read their current content (maximum 1 MiB). "
                "Sharing metadata describes manageable direct group and user sharing, not a full effective-access audit."
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
            explorer = BrowsingExplorer(self._services.browsing())
            if isinstance(command, ResolveHome):
                node = await self._services.homes().get_or_provision(caller)
                operation_completed()
                nodes = await enrich_nodes(self._services.sharing(), caller, [node], self._services.access())
                breadcrumbs = await self._services.browsing().get_breadcrumbs(caller, node.id)
                inspection = FilesystemNodeInspection(node=nodes[0], breadcrumbs=breadcrumbs)
                response = HomeResponse(operation="home", result=inspection)
                rendered = render_inspection(inspection)
            elif isinstance(command, InspectNode):
                inspection = await explorer.inspect_node(caller, command.target)
                operation_completed()
                nodes = await enrich_nodes(self._services.sharing(), caller, [inspection.node], self._services.access())
                inspection = FilesystemNodeInspection(node=nodes[0], breadcrumbs=inspection.breadcrumbs)
                response = NodeInspectionResponse(operation="stat", result=inspection)
                rendered = render_inspection(inspection)
            elif isinstance(command, ReadTree):
                tree = await explorer.read_tree(
                    caller, command.target, TreeLimits(depth=command.depth, max_entries=command.max_entries),
                )
                operation_completed()
                nodes = await enrich_nodes(
                    self._services.sharing(), caller, [tree.node, *(entry.node for entry in tree.entries)], self._services.access(),
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
                    caller, command.target, ListingLimits(max_entries=command.max_entries),
                )
                operation_completed()
                nodes = await enrich_nodes(
                    self._services.sharing(), caller, [listing.node, *listing.entries], self._services.access(),
                )
                listing = FilesystemDirectoryListing(
                    node=nodes[0], breadcrumbs=listing.breadcrumbs,
                    entries=nodes[1:], truncated=listing.truncated,
                )
                response = DirectoryListingResponse(operation="ls", result=listing)
                rendered = render_listing(listing)
            return file_link_result(response, nodes, rendered)
