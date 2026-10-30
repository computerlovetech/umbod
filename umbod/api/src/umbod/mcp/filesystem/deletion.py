import json
from typing import Any

from fastmcp.exceptions import ValidationError
from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr

from .authorization import root_filesystem_tool_access
from .errors import filesystem_operation
from .models import DeleteFileCommand, FileDeletionResult
from .ports import FilesystemCallerCapture, FilesystemServiceFactory


class FilesystemDeleteFileTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_delete_file",
            description=(
                "Permanently remove one file's namespace entry, ownership and direct grants. "
                "Requires its UUID and current revision from filesystem browsing; stale revisions fail. "
                "Directories, the root and recursive deletion are unsupported. "
                "Does not erase stored bytes or provide trash or restore. "
                "Retrying a successful deletion fails because the file no longer exists."
            ),
            parameters=DeleteFileCommand.model_json_schema(),
            output_schema=FileDeletionResult.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False,
            ),
            auth=root_filesystem_tool_access,
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = DeleteFileCommand.model_validate_json(json.dumps(arguments, allow_nan=False))
        except (TypeError, ValueError):
            raise ValidationError("filesystem_invalid_delete: Invalid file deletion arguments") from None
        with filesystem_operation():
            caller = self._callers.capture()
            await self._services.deletion().delete_file(
                caller, command.node_id, expected_revision=command.expected_revision,
            )
            result = FileDeletionResult(node_id=command.node_id, deleted=True)
            return ToolResult(
                content="File deleted successfully.",
                structured_content=result.model_dump(mode="json"),
            )
