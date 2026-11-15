from typing import Any
from uuid import UUID

from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import Field, PrivateAttr

from umbod.core.filesystem.updates import NodeChanges

from .argument_errors import argument_json
from umbod.mcp.responses.progress import operation_completed

from .errors import filesystem_operation
from .links import file_link_result
from .models import FilesystemNodeSummary
from .ports import FilesystemCallerCapture, FilesystemServiceFactory
from .sharing import enrich_projected_nodes


class UpdateNodeCommand(NodeChanges):
    node_id: UUID
    expected_revision: int = Field(ge=1, le=9_999_999_999_999_999_999, strict=True)


class FilesystemUpdateNodeTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="update_filesystem_node",
            description=(
                "Atomically update a file or directory name, parent or metadata with its current revision. "
                "Provide at least one of name, parent_id or metadata; empty updates are invalid. "
                "Omitted fields and bytes are preserved. Requires discover and write on the item; "
                "moving also requires discover and write on both current and destination directories. "
                "Moves must stay within the same namespace and preserve its baseline policy and direct item grants. "
                "Before moving, warn that recursive folder access follows the destination and may change the audience. "
                "Namespace root metadata may change, but roots cannot be renamed or moved. "
                "An empty attributes.description clears the description. Returns file resource links when discover access remains. "
                "view_url opens the authenticated Umbod browser view, not a public share, download, or MCP resource read; null when discovery is lost. "
                "Permissions and visibility reflect the committed update transaction; later policy changes require fresh inspection. "
                "A successful update may return can_discover=false if discovery is revoked concurrently; "
                "the update is complete and must not be retried for that reason."
            ),
            parameters=UpdateNodeCommand.model_json_schema(),
            output_schema=FilesystemNodeSummary.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False,
            ),
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        command = UpdateNodeCommand.model_validate_json(argument_json(arguments, allow_nan=True))
        with filesystem_operation():
            caller = self._callers.capture()
            node = await self._services.updates().update_node(
                caller, command.node_id, command.to_core_patch(), expected_revision=command.expected_revision,
            )
            operation_completed()
            result = (await enrich_projected_nodes(self._services.sharing(), caller, [node], self._services.view_url))[0]
            return file_link_result(
                result, [result] if result.permissions.can_discover else [], result.model_dump_json(), self._services.read_max_bytes(),
            )
