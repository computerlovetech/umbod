from typing import Any

from fastmcp.tools import InputRequiredToolResult
from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr

from umbod.core.filesystem.errors import RevisionConflict

from .approval_state import FileDeletionApprovalDenied
from .argument_errors import argument_json
from umbod.mcp.responses.progress import operation_completed, operation_started

from .errors import filesystem_preflight
from .models import DeleteFileCommand, FileDeletionResult
from .ports import (
    FileDeletionApproval, FilesystemCallerCapture, FilesystemDeletionApproval, FilesystemServiceFactory,
)


class FilesystemDeleteFileTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()
    _approval: FilesystemDeletionApproval = PrivateAttr()

    def __init__(
        self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory,
        approval: FilesystemDeletionApproval,
    ) -> None:
        super().__init__(
            name="filesystem_delete_file",
            description=(
                "Permanently remove one file's namespace entry, ownership and direct grants. "
                "Requires its UUID, current revision from filesystem browsing and explicit human confirmation. "
                "Declined, unavailable or expired approval never deletes the file; stale revisions fail. "
                "Directories, the root and recursive deletion are unsupported. "
                "Does not erase stored bytes or provide trash or restore. "
                "Retrying a successful deletion fails because the file no longer exists."
            ),
            parameters=DeleteFileCommand.model_json_schema(),
            output_schema=FileDeletionResult.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False,
            ),
        )
        self._callers = callers
        self._services = services
        self._approval = approval

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        command = DeleteFileCommand.model_validate_json(argument_json(arguments, allow_nan=False))
        with filesystem_preflight():
            caller = self._callers.capture()
            deletion = self._services.deletion()
            await deletion.check_delete_eligibility(caller, command.node_id)
            node = await self._services.browsing().get_node(caller, command.node_id)
            if node.revision != command.expected_revision:
                raise RevisionConflict(str(command.node_id))
            approval = await self._approval.confirm(caller, command, node)
            if isinstance(approval, InputRequiredToolResult):
                return approval
            if approval is not FileDeletionApproval.APPROVED:
                raise FileDeletionApprovalDenied()
            current_caller = self._callers.capture()
            if current_caller.caller != caller.caller:
                raise FileDeletionApprovalDenied()
            operation_started()
            await deletion.delete_file(
                current_caller, command.node_id, expected_revision=command.expected_revision,
            )
            operation_completed()
            result = FileDeletionResult(node_id=command.node_id, deleted=True)
            return ToolResult(
                content="File deleted successfully.",
                structured_content=result.model_dump(mode="json"),
            )
