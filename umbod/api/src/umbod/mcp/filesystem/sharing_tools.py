from typing import Any

from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr, TypeAdapter

from umbod.core.filesystem.access import RestrictedVisibility
from umbod.core.filesystem.authorization import PermissionDenied
from umbod.core.filesystem.sharing import (
    GroupSharingTarget, ShareNodePolicy, SharingRecipientSearchQuery,
    SharingRecipientSearchResult, SharingScope,
)

from .argument_errors import argument_json
from umbod.mcp.responses.progress import operation_completed

from .errors import filesystem_operation
from .ports import FilesystemCallerCapture, FilesystemServiceFactory
from .sharing_models import (
    SEARCH_RECIPIENTS_COMMAND, SHARE_COMMAND, FilteredSearchSharingRecipientsCommand,
    LegacyShareNodeGroupResult, ShareNodeGroupCommand, CallerShareNodeResult,
)


class FilesystemSearchSharingRecipientsTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_search_sharing_recipients",
            description=(
                "Search eligible registered groups and observed users for direct sharing of a file or directory. "
                "Requires current discover and share authority, direct or inherited from recursive directory grants. User discovery requires verified "
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
        command = SEARCH_RECIPIENTS_COMMAND.validate_json(argument_json(arguments, allow_nan=False))
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
            operation_completed()
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
                "Requires current discover and share authority, direct or inherited, on every invocation. "
                "Request discover and read together for normal read access. "
                "New directory grants default to recursive=true, applying to current and future descendants. "
                "Omitting recursive preserves the scope of an existing grant. "
                "Set recursive=false for this node only; file grants always return recursive=false. "
                "Additive sharing preserves existing recursive scope and never transfers ownership. "
                "Find recipients with filesystem_search_sharing_recipients. Use the returned type and "
                "group_id or user_id in recipient, omitting the display label. "
                "Legacy top-level group_id requests retain their original response shape."
            ),
            parameters={"type": "object", **SHARE_COMMAND.json_schema()},
            output_schema={"type": "object", **TypeAdapter(CallerShareNodeResult | LegacyShareNodeGroupResult).json_schema()},
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False,
            ),
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        command = SHARE_COMMAND.validate_json(argument_json(arguments, allow_nan=False))
        with filesystem_operation():
            snapshot = self._callers.capture()
            recipient = (
                GroupSharingTarget(type="group", group_id=command.group_id)
                if isinstance(command, ShareNodeGroupCommand) else command.recipient
            )
            policy = ShareNodePolicy.model_validate({
                "recipient": recipient, "permissions": command.permissions,
                **({"recursive": command.recursive} if "recursive" in command.model_fields_set else {}),
            })
            result = await self._services.sharing().share(snapshot, command.node_id, policy)
            operation_completed()
            try:
                node = await self._services.browsing().get_node(snapshot, command.node_id)
                visible_to = (await self._services.access().enrich_nodes(snapshot, [node]))[0].visible_to
            except PermissionDenied:
                visible_to = RestrictedVisibility(type="restricted")
            result = CallerShareNodeResult(**result.model_dump(), visible_to=visible_to)
            if isinstance(command, ShareNodeGroupCommand):
                result = LegacyShareNodeGroupResult(
                    node_id=result.node_id, group_id=command.group_id,
                    permissions=result.permissions, recursive=result.recursive, changed=result.changed, visible_to=visible_to,
                )
            return ToolResult(
                content=result.model_dump_json(),
                structured_content=result.model_dump(mode="json"),
            )
