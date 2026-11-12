from typing import Any
from urllib.parse import urlsplit

from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr

from umbod.core.filesystem.uploads.errors import UploadExpired, UploadReceiptUnavailable
from umbod.core.filesystem.uploads.models import ExpectedChecksum, NoExpectedChecksum, VerifiedReceipt, UnavailableExternalTransfer, ExternalTransfer

from umbod.mcp.responses.progress import operation_completed

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
                "Follow the returned PUT instructions: S3 uses a presigned storage URL; other backends use an API capability. "
                "Treat the whole returned URL as sensitive. Transfer raw bytes once, then call "
                "filesystem_complete_upload. Never send MCP bearer credentials or follow redirects. "
                "Compute local file size and SHA256 programmatically; do not reproduce file bytes in model output. "
                "Beginning is not idempotent. After an uncertain S3 PUT, call filesystem_complete_upload with the same "
                "upload ID to verify stored bytes; S3 session status stays pending until verification. Never blindly replay "
                "the PUT or begin a replacement. For API capability transfers, inspect progress with an authenticated "
                "HTTP GET to /api/filesystem/uploads/{upload_id} before replaying. "
                "Capability expiry does not imply session expiry. A process crash during API transfer leaves a conflict."
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
        command = BeginUploadCommand.model_validate(arguments)
        with filesystem_operation():
            expected = NoExpectedChecksum() if command.expected_sha256 == "" else ExpectedChecksum(
                sha256=command.expected_sha256,
            )
            uploads = self._services.upload_sessions()
            if uploads.supports_external_transfer:
                session = await uploads.begin_transfer(
                    self._callers.capture(), command.parent_id, command.name, command.metadata,
                    command.size_bytes, expected,
                )
                operation_completed()
                instructions = await uploads.transfer_instructions(session)
                if isinstance(instructions, UnavailableExternalTransfer) or not isinstance(session.delegated_transfer, ExternalTransfer):
                    raise UploadExpired()
                response = BeginUploadResult(
                    upload_id=session.id, expires_at=session.delegated_transfer.expires_at,
                    transfer=CapabilityTransfer(url=instructions.url, headers=instructions.headers),
                )
                return ToolResult(structured_content=response.model_dump(mode="json"))
            origin = validated_api_origin(self._services.upload_api_origin())
            result = await uploads.begin_delegated(
                self._callers.capture(), command.parent_id, command.name, command.metadata,
                command.size_bytes, expected,
            )
            operation_completed()
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
                "Replay a known completed upload with the same upload ID to retrieve its persisted verified receipt "
                "and file identity. Deleted files are not restored; deleted or legacy-unverified receipts cannot "
                "provide a verified completion result. Inspect session progress before replaying an uncertain "
                "transfer or beginning another upload. Capability expiry does not imply session expiry; "
                "complete an already staged upload with the same ID."
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
        command = CompleteUploadCommand.model_validate(arguments)
        with filesystem_operation():
            caller = self._callers.capture()
            result = await self._services.upload_sessions().complete_verified(caller, command.upload_id)
            operation_completed()
            if not isinstance(result.receipt, VerifiedReceipt):
                raise UploadReceiptUnavailable()
            node = (await enrich_nodes(self._services.sharing(), caller, [result.node], self._services.access()))[0]
            response = CompleteUploadResult(
                node=node, size_bytes=result.receipt.size_bytes, sha256=result.receipt.sha256,
            )
            return file_link_result(response, [node], response.model_dump_json(), self._services.read_max_bytes())
