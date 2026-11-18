import json
from collections.abc import Callable
from typing import Union

from fastmcp.exceptions import AuthorizationError
from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_access_token, get_context
from fastmcp.tools import InputRequiredToolResult
from mcp.shared.exceptions import MCPError
from mcp.types import ElicitRequest, ElicitRequestFormParams, ElicitResult, InputRequiredResult

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.invocation import ApprovalNonceConsumption, ApprovalNonceStore

from .approval_state import FileDeletionApprovalDenied, FileDeletionApprovalStateCodec
from .models import DeleteFileCommand, FileDeletionConfirmation
from .ports import FileDeletionApproval


_APPROVAL_REQUEST_KEY = "filesystem_delete_approval"


class McpFilesystemDeletionApproval:
    def __init__(
        self,
        nonce_store: ApprovalNonceStore,
        clock: Callable[[], float],
        random_token: Callable[[], str],
    ) -> None:
        self._nonce_store = nonce_store
        self._state_codec = FileDeletionApprovalStateCodec(clock, random_token)

    async def confirm(
        self, caller: CallerSnapshot, command: DeleteFileCommand, node: NodeSummary
    ) -> Union[FileDeletionApproval, InputRequiredToolResult]:
        try:
            context = get_context()
            request = getattr(context.request_context, "request", None)
            if getattr(getattr(request, "params", None), "name", None) == "execute_code":
                raise FileDeletionApprovalDenied("File deletion approval unavailable")
            message = self._message(command, node)
            if context._is_modern_protocol():
                token = get_access_token()
                client_id = token.client_id if token else ""
                return await self._confirm_modern(context, caller, command, client_id, message)
            response = await context.elicit(message, FileDeletionConfirmation)
            confirmation = getattr(response, "data", None)
            if (
                getattr(response, "action", None) != "accept"
                or not isinstance(confirmation, FileDeletionConfirmation)
                or confirmation.value is not True
            ):
                raise FileDeletionApprovalDenied("File deletion approval denied")
            return FileDeletionApproval.APPROVED
        except (MCPError, AuthorizationError):
            raise
        except Exception:
            raise FileDeletionApprovalDenied("File deletion approval denied") from None

    async def _confirm_modern(
        self,
        context: Context,
        caller: CallerSnapshot,
        command: DeleteFileCommand,
        client_id: str,
        message: str,
    ) -> Union[FileDeletionApproval, InputRequiredToolResult]:
        request_state = context.request_state
        responses = context.input_responses
        if (request_state is None) != (responses is None):
            raise FileDeletionApprovalDenied("File deletion approval continuation invalid")
        if request_state is None:
            return InputRequiredToolResult(
                InputRequiredResult(
                    inputRequests={
                        _APPROVAL_REQUEST_KEY: ElicitRequest(
                            params=ElicitRequestFormParams(
                                message=message,
                                requestedSchema={
                                    "type": "object",
                                    "properties": {"value": {"type": "boolean"}},
                                    "required": ["value"],
                                },
                            )
                        )
                    },
                    requestState=self._state_codec.mint(caller, command, client_id),
                )
            )
        if not isinstance(responses, dict) or set(responses) != {_APPROVAL_REQUEST_KEY}:
            raise FileDeletionApprovalDenied("File deletion approval response invalid")
        response = responses[_APPROVAL_REQUEST_KEY]
        if (
            not isinstance(response, ElicitResult)
            or response.action != "accept"
            or response.content is None
            or response.content.get("value") is not True
        ):
            raise FileDeletionApprovalDenied("File deletion approval denied")
        state = self._state_codec.verify(request_state, caller, command, client_id)
        if not await self._nonce_store.consume(
            ApprovalNonceConsumption(nonce=state.nonce, expires_at=state.expires_at)
        ):
            raise FileDeletionApprovalDenied("File deletion approval already consumed")
        return FileDeletionApproval.APPROVED

    @staticmethod
    def _message(command: DeleteFileCommand, node: NodeSummary) -> str:
        return (
            f"Permanently delete file {json.dumps(node.name, ensure_ascii=True)} "
            f"(UUID {command.node_id}, expected_revision {command.expected_revision})? "
            "This permanently removes its namespace entry, ownership, and grants. "
            "There is no trash or restore. Stored bytes are not erased."
        )
