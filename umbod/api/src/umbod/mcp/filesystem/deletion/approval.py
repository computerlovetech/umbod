import json
from collections.abc import Callable, Mapping
from typing import Union

from fastmcp.server.dependencies import get_access_token, get_context
from fastmcp.tools import InputRequiredToolResult
from mcp.shared.exceptions import NoBackChannelError
from mcp.types import ElicitRequest, ElicitRequestFormParams, ElicitResult, InputRequiredResult, InputResponses

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.invocation import ApprovalNonceConsumption, ApprovalNonceStore

from .approval_state import (
    FileDeletionApprovalDenied, FileDeletionApprovalStateCodec, FileDeletionApprovalUnavailable,
)
from .models import DeleteFileCommand, FileDeletionConfirmation
from .ports import FileDeletionApproval, FileDeletionApprovalPolicy


_APPROVAL_REQUEST_KEY = "filesystem_delete_approval"


class McpFilesystemDeletionApproval:
    def __init__(
        self,
        nonce_store: ApprovalNonceStore,
        clock: Callable[[], float],
        random_token: Callable[[], str],
        *, policy: FileDeletionApprovalPolicy,
    ) -> None:
        self._nonce_store = nonce_store
        self._policy = policy
        self._state_codec = FileDeletionApprovalStateCodec(clock, random_token)

    async def confirm(
        self, caller: CallerSnapshot, command: DeleteFileCommand, node: NodeSummary
    ) -> Union[FileDeletionApproval, InputRequiredToolResult]:
        context = get_context()
        request = getattr(context.request_context, "_srctx", None)
        params = getattr(request, "params", None)
        tool_name = params.get("name") if isinstance(params, Mapping) else None
        if tool_name == "execute_code":
            raise FileDeletionApprovalDenied("File deletion approval unavailable")
        modern = context._is_modern_protocol()
        request_state = context.request_state
        responses = context.input_responses
        if request_state is not None or responses is not None or self._has_continuation_fields(params):
            if not modern or request_state is None or responses is None:
                raise FileDeletionApprovalDenied("File deletion approval continuation invalid")
            return await self._resume_modern(caller, command, self._client_id(), request_state, responses)
        if (
            getattr(request, "method", None) == "tools/call"
            and tool_name == "filesystem_delete_file"
            and await self._policy.requires_mcp_file_deletion_approval() is False
        ):
            return FileDeletionApproval.APPROVED
        message = self._message(command, node)
        if modern:
            return self._request_modern(caller, command, self._client_id(), message)
        try:
            response = await context.elicit(message, FileDeletionConfirmation)
        except NoBackChannelError:
            raise FileDeletionApprovalUnavailable() from None
        confirmation = getattr(response, "data", None)
        if (
            getattr(response, "action", None) != "accept"
            or not isinstance(confirmation, FileDeletionConfirmation)
            or confirmation.value is not True
        ):
            raise FileDeletionApprovalDenied("File deletion approval denied")
        return FileDeletionApproval.APPROVED

    def _request_modern(
        self,
        caller: CallerSnapshot,
        command: DeleteFileCommand,
        client_id: str,
        message: str,
    ) -> InputRequiredToolResult:
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

    async def _resume_modern(
        self,
        caller: CallerSnapshot,
        command: DeleteFileCommand,
        client_id: str,
        request_state: str,
        responses: InputResponses,
    ) -> FileDeletionApproval:
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
    def _client_id() -> str:
        token = get_access_token()
        return token.client_id if token else ""

    @staticmethod
    def _has_continuation_fields(params: object) -> bool:
        return isinstance(params, Mapping) and not {"requestState", "inputResponses"}.isdisjoint(params)

    @staticmethod
    def _message(command: DeleteFileCommand, node: NodeSummary) -> str:
        return (
            f"Permanently delete file {json.dumps(node.name, ensure_ascii=True)} "
            f"(UUID {command.node_id}, expected_revision {command.expected_revision})? "
            "This permanently removes its namespace entry, ownership, and grants. "
            "There is no trash or restore. Stored bytes are not erased."
        )
