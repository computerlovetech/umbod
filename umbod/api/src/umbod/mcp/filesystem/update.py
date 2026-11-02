import json
from typing import Any
from uuid import UUID

from fastmcp.exceptions import ValidationError
from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import Field, PrivateAttr, ValidationError as ModelValidationError

from umbod.core.filesystem.updates import NodeChanges

from .errors import filesystem_operation
from .links import file_link_result
from .models import FilesystemNodeSummary
from .ports import FilesystemCallerCapture, FilesystemServiceFactory
from .sharing import enrich_nodes


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
                "Omitted fields, bytes, ownership and grants are preserved. Requires discover and write on the item; "
                "moving also requires discover and write on both current and destination directories. "
                "Root metadata may change, but root cannot be renamed or moved. "
                "An empty attributes.description clears the description. Returns current file resource links."
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
        try:
            command = UpdateNodeCommand.model_validate_json(json.dumps(arguments))
        except ModelValidationError as error:
            raise ValidationError(str(error)) from None
        with filesystem_operation():
            caller = self._callers.capture()
            node = await self._services.updates().update_node(
                caller, command.node_id, command.to_core_patch(), expected_revision=command.expected_revision,
            )
            result = (await enrich_nodes(self._services.sharing(), caller, [node]))[0]
            return file_link_result(result, [result], result.model_dump_json())
