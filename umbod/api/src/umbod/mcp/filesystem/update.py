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
                "Omitted fields, bytes, ownership and grants are preserved. Requires discover and write on the item; "
                "moving also requires discover and write on both current and destination directories. "
                "Before moving, warn the user that inherited access may change while direct sharing remains unchanged. "
                "A move replaces source-folder inheritance with destination-folder inheritance for the item and its contents. "
                "Root metadata may change, but root cannot be renamed or moved. "
                "An empty attributes.description clears the description. Returns file resource links when discover access remains. "
                "Permissions and visibility reflect the committed update transaction; later policy changes require fresh inspection. "
                "A successful move may return can_discover=false when the caller loses inherited access; "
                "the move is complete and must not be retried for that reason."
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
            result = (await enrich_projected_nodes(self._services.sharing(), caller, [node]))[0]
            return file_link_result(
                result, [result] if result.permissions.can_discover else [], result.model_dump_json(),
            )
