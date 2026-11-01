import json
from typing import Any

from fastmcp.exceptions import ValidationError
from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr, TypeAdapter

from umbod.core.filesystem.sharing import (
    GroupSharingTarget, ShareNodePolicy, ShareNodeResult, SharingRecipientSearchQuery,
    SharingRecipientSearchResult, SharingScope,
)

from .errors import filesystem_operation
from .ports import FilesystemCallerCapture, FilesystemServiceFactory
from .sharing_models import (
    SEARCH_RECIPIENTS_COMMAND, SHARE_COMMAND, FilteredSearchSharingRecipientsCommand,
    LegacyShareNodeGroupResult, ShareNodeGroupCommand,
)


class FilesystemSearchSharingRecipientsTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_search_sharing_recipients",
            description=(
                "Search eligible registered groups and observed users for direct sharing of a file or directory. "
                "Requires current direct-node discover and share authority. User discovery requires verified "
                "authentication under the configured issuer. Query matches group IDs or labels and observed "
                "user names as a case-insensitive literal substring, with normalized whitespace. "
                "Query must be nonblank and at most 200 characters. Omit recipient_type to search both types. "
                "Returns at most 50 eligible recipients, groups first, with has_more. "
                "Does not create recipients or grant access; the observed directory may be incomplete."
            ),
            parameters={"type": "object", **SEARCH_RECIPIENTS_COMMAND.json_schema()},
            output_schema=SharingRecipientSearchResult.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
            ),
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = SEARCH_RECIPIENTS_COMMAND.validate_json(json.dumps(arguments, allow_nan=False))
        except (TypeError, ValueError):
            raise ValidationError("filesystem_invalid_sharing: Invalid filesystem sharing arguments") from None
        with filesystem_operation():
            snapshot = self._callers.capture()
            recipient_types = (
                frozenset({command.recipient_type})
                if isinstance(command, FilteredSearchSharingRecipientsCommand)
                else frozenset({"group", "user"})
            )
            query = SharingRecipientSearchQuery(
                query=command.query, scope=SharingScope(recipient_types=recipient_types),
            )
            result = await self._services.sharing().search_recipients(snapshot, command.node_id, query)
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
                "Add explicit permissions for one registered group or observed user on a file or directory. "
                "Unions permissions with the recipient's existing manageable direct grant; "
                "preserves other permissions and recipients. Retrying is idempotent. "
                "Requires current direct-node discover and share authority on every invocation. "
                "Request discover and read together for normal read access. "
                "Applies only to this node, not descendants; never transfers ownership. "
                "Find recipients with filesystem_search_sharing_recipients. Use the returned type and "
                "group_id or user_id in recipient, omitting the display label. No inheritance or recursive sharing. "
                "Legacy top-level group_id requests retain their original response shape."
            ),
            parameters={"type": "object", **SHARE_COMMAND.json_schema()},
            output_schema={"type": "object", **TypeAdapter(ShareNodeResult | LegacyShareNodeGroupResult).json_schema()},
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False,
            ),
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = SHARE_COMMAND.validate_json(json.dumps(arguments, allow_nan=False))
        except (TypeError, ValueError):
            raise ValidationError("filesystem_invalid_sharing: Invalid filesystem sharing arguments") from None
        with filesystem_operation():
            snapshot = self._callers.capture()
            recipient = (
                GroupSharingTarget(type="group", group_id=command.group_id)
                if isinstance(command, ShareNodeGroupCommand) else command.recipient
            )
            policy = ShareNodePolicy(recipient=recipient, permissions=command.permissions)
            result = await self._services.sharing().share(snapshot, command.node_id, policy)
            if isinstance(command, ShareNodeGroupCommand):
                result = LegacyShareNodeGroupResult(
                    node_id=result.node_id, group_id=command.group_id,
                    permissions=result.permissions, changed=result.changed,
                )
            return ToolResult(
                content=result.model_dump_json(),
                structured_content=result.model_dump(mode="json"),
            )
