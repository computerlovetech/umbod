from typing import Any
from urllib.parse import urlsplit

from fastmcp.exceptions import ValidationError
from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr, ValidationError as ModelValidationError

from umbod.core.filesystem.uploads.errors import UploadReceiptUnavailable
from umbod.core.filesystem.uploads.models import ExpectedChecksum, NoExpectedChecksum, VerifiedReceipt

from .errors import filesystem_operation
from .links import file_link_result
from .ports import FilesystemCallerCapture, FilesystemServiceFactory
from .sharing import enrich_nodes
from .upload_session_models import (
    BeginUploadCommand, BeginUploadResult, CapabilityTransfer, CompleteUploadCommand, CompleteUploadResult,
)


UPLOAD_TOKEN_HEADER = "X-Umbod-Upload-Token"


def validated_api_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        not parsed.hostname or parsed.username is not None or parsed.password is not None
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or (parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")
        ))
    ):
        raise ValueError("Upload requires a configured HTTPS or localhost API origin")
    parsed.port
    return value.rstrip("/")


class FilesystemBeginUploadTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_begin_upload",
            description=(
                "Begin a private filesystem upload using the configured server size limit. "
                "Transfer raw bytes once via the returned capability-only HTTP PUT, then call "
                "filesystem_complete_upload. Never send MCP bearer credentials or follow redirects. "
                "Compute local file size and SHA256 programmatically; do not reproduce file bytes in model output. "
                "Not idempotent. Failed transfers may retry; a process crash during transfer leaves a conflict."
            ),
            parameters=BeginUploadCommand.model_json_schema(),
            output_schema=BeginUploadResult.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False,
            ),
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = BeginUploadCommand.model_validate(arguments)
        except ModelValidationError:
            raise ValidationError("filesystem_invalid_upload: Invalid upload arguments") from None
        with filesystem_operation():
            origin = validated_api_origin(self._services.upload_api_origin())
            expected = NoExpectedChecksum() if command.expected_sha256 == "" else ExpectedChecksum(
                sha256=command.expected_sha256,
            )
            result = await self._services.upload_sessions().begin_delegated(
                self._callers.capture(), command.parent_id, command.name, command.metadata,
                command.size_bytes, expected,
            )
            content_type = command.metadata.content_type
            response = BeginUploadResult(
                upload_id=result.session.id, expires_at=result.expires_at,
                transfer=CapabilityTransfer(
                    url=f"{origin}/api/filesystem/uploads/{result.session.id}/transfer",
                    headers={
                        UPLOAD_TOKEN_HEADER: result.token,
                        "Content-Type": content_type if isinstance(content_type, str) else "application/octet-stream",
                    },
                ),
            )
            return ToolResult(structured_content=response.model_dump(mode="json"))


class FilesystemCompleteUploadTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_complete_upload",
            description=(
                "Publish a staged private file using the current authenticated caller. "
                "Returns node metadata, verified byte count and SHA256, and a native MCP resource link. "
                "Retries return the persisted receipt and file identity; deleted files are not restored."
            ),
            parameters=CompleteUploadCommand.model_json_schema(),
            output_schema=CompleteUploadResult.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False,
            ),
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = CompleteUploadCommand.model_validate(arguments)
        except ModelValidationError:
            raise ValidationError("filesystem_invalid_upload: Invalid upload arguments") from None
        with filesystem_operation():
            caller = self._callers.capture()
            result = await self._services.upload_sessions().complete_verified(caller, command.upload_id)
            if not isinstance(result.receipt, VerifiedReceipt):
                raise UploadReceiptUnavailable()
            node = (await enrich_nodes(self._services.sharing(), caller, [result.node], self._services.access()))[0]
            response = CompleteUploadResult(
                node=node, size_bytes=result.receipt.size_bytes, sha256=result.receipt.sha256,
            )
            return file_link_result(response, [node], response.model_dump_json())
