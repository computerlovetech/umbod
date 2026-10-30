from typing import Any

from fastmcp.exceptions import ValidationError
from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr, ValidationError as ModelValidationError

from umbod.core.filesystem.browsing import NodeSummary
from umbod.core.filesystem.content.errors import UploadTooLarge
from umbod.core.filesystem.ports import ByteStream

from .authorization import root_filesystem_tool_access
from .errors import filesystem_operation
from .ports import FilesystemCallerCapture, FilesystemServiceFactory
from .upload_models import MAX_UPLOAD_BYTES, UploadCommand


async def content_stream(content: bytes) -> ByteStream:
    yield content


class FilesystemUploadTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_upload",
            description=(
                "Create a private file with UTF-8 text or canonical padded base64 content. "
                "Maximum 10485760 decoded bytes (10 MiB); lower server limits apply. "
                "One-shot upload, without chunking or resumability. Retrying is not idempotent. "
                "Returns file metadata only, never uploaded content."
            ),
            parameters=UploadCommand.model_json_schema(),
            output_schema=NodeSummary.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False,
            ),
            auth=root_filesystem_tool_access,
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = UploadCommand.model_validate(arguments)
            content = command.content.decode()
        except (ModelValidationError, ValueError, UnicodeError):
            raise ValidationError("filesystem_invalid_upload: Invalid upload arguments") from None
        except UploadTooLarge:
            with filesystem_operation():
                raise
        with filesystem_operation():
            if len(content) > MAX_UPLOAD_BYTES:
                raise UploadTooLarge()
            caller = self._callers.capture()
            uploads = self._services.uploads()
            session = await uploads.begin(
                caller, command.parent_id, command.name, command.metadata, len(content),
            )
            content_type = command.metadata.content_type
            await uploads.put(
                caller, session.id,
                content_type if isinstance(content_type, str) else "application/octet-stream",
                content_stream(content),
            )
            result = await uploads.complete(caller, session.id)
            return ToolResult(
                content="File uploaded successfully.",
                structured_content=result.node.model_dump(mode="json"),
            )
