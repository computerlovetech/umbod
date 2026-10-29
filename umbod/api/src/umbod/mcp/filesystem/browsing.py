import json
from typing import Any

from fastmcp.exceptions import ValidationError
from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr, ValidationError as ModelValidationError

from umbod.core.filesystem.browsing.exploration import BrowsingExplorer, ListingLimits, TreeLimits

from .authorization import root_filesystem_tool_access
from .browsing_models import (
    BROWSE_COMMAND,
    BROWSE_RESPONSE,
    DirectoryListingResponse,
    DirectoryTreeResponse,
    InspectNode,
    NodeInspectionResponse,
    ReadTree,
    browse_input_schema,
)
from .errors import filesystem_operation
from .ports import FilesystemCallerCapture, FilesystemServiceFactory
from .rendering import render_inspection, render_listing, render_tree


class FilesystemBrowseTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_browse",
            description=(
                "Browse the remote Umbod filesystem, not the server host. "
                "Declare ls for immediate entries, tree for a bounded recursive overview, "
                "or stat for node details. Target root, an absolute path, or a node UUID. "
                "No working directory or shell execution. Only discoverable nodes are returned; "
                "breadcrumbs may be partial. Limits bound returned entries, not storage work. "
                "Separate reads may observe concurrent changes. No file bytes are read."
            ),
            parameters=browse_input_schema(),
            output_schema={"type": "object", **BROWSE_RESPONSE.json_schema()},
            annotations=ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
            ),
            auth=root_filesystem_tool_access,
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = BROWSE_COMMAND.validate_json(json.dumps(arguments))
        except ModelValidationError as error:
            raise ValidationError(str(error)) from None
        with filesystem_operation():
            caller = self._callers.capture()
            explorer = BrowsingExplorer(self._services.browsing())
            if isinstance(command, InspectNode):
                inspection = await explorer.inspect_node(caller, command.target)
                response = NodeInspectionResponse(operation="stat", result=inspection)
                rendered = render_inspection(inspection)
            elif isinstance(command, ReadTree):
                tree = await explorer.read_tree(
                    caller, command.target, TreeLimits(depth=command.depth, max_entries=command.max_entries),
                )
                response = DirectoryTreeResponse(operation="tree", result=tree)
                rendered = render_tree(tree)
            else:
                listing = await explorer.list_directory(
                    caller, command.target, ListingLimits(max_entries=command.max_entries),
                )
                response = DirectoryListingResponse(operation="ls", result=listing)
                rendered = render_listing(listing)
            return ToolResult(content=rendered, structured_content=response.model_dump(mode="json"))
