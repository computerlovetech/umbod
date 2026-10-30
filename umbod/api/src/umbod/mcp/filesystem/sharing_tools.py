import json
from typing import Any

from fastmcp.exceptions import ValidationError
from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr

from umbod.core.filesystem.sharing import EligibleSharingGroups, GroupPolicy, ShareNodeGroupResult

from .authorization import root_filesystem_tool_access
from .errors import filesystem_operation
from .ports import FilesystemCallerCapture, FilesystemServiceFactory
from .sharing_models import ListSharingGroupsCommand, ShareNodeGroupCommand


class FilesystemListSharingGroupsTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_list_sharing_groups",
            description=(
                "List registered groups eligible for direct sharing of a file or directory. "
                "Requires current direct-node discover and share authority. "
                "Returns current group labels and descriptions, not login observations. "
                "Does not create groups or support user sharing."
            ),
            parameters=ListSharingGroupsCommand.model_json_schema(),
            output_schema=EligibleSharingGroups.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
            ),
            auth=root_filesystem_tool_access,
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = ListSharingGroupsCommand.model_validate_json(json.dumps(arguments, allow_nan=False))
        except (TypeError, ValueError):
            raise ValidationError("filesystem_invalid_sharing: Invalid filesystem sharing arguments") from None
        with filesystem_operation():
            snapshot = self._callers.capture()
            result = await self._services.sharing().eligible_groups(snapshot, command.node_id)
            return ToolResult(
                content=result.model_dump_json(),
                structured_content=result.model_dump(mode="json"),
            )


class FilesystemShareTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_share",
            description=(
                "Add explicit permissions for one registered group on a file or directory. "
                "Unions permissions with the group's existing manageable direct grant; "
                "preserves other permissions and groups. Retrying is idempotent. "
                "Requires current direct-node discover and share authority on every invocation. "
                "Request discover and read together for normal read access. "
                "Applies only to this node, not descendants; never transfers ownership. "
                "Preserve the exact group ID from filesystem_list_sharing_groups. "
                "Does not create groups or support user sharing."
            ),
            parameters=ShareNodeGroupCommand.model_json_schema(),
            output_schema=ShareNodeGroupResult.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False,
            ),
            auth=root_filesystem_tool_access,
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = ShareNodeGroupCommand.model_validate_json(json.dumps(arguments, allow_nan=False))
        except (TypeError, ValueError):
            raise ValidationError("filesystem_invalid_sharing: Invalid filesystem sharing arguments") from None
        with filesystem_operation():
            snapshot = self._callers.capture()
            policy = GroupPolicy(group_id=command.group_id, permissions=command.permissions)
            result = await self._services.sharing().share(snapshot, command.node_id, policy)
            return ToolResult(
                content=result.model_dump_json(),
                structured_content=result.model_dump(mode="json"),
            )
