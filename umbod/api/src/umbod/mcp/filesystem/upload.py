from typing import Any

from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr, ValidationError as ModelValidationError

from umbod.core.filesystem.access import CallerNodeSummary
from umbod.core.filesystem.content.errors import UploadTooLarge
from umbod.core.filesystem.ports import ByteStream

from .argument_errors import invalid_content_error
from umbod.mcp.responses.progress import operation_completed

from .errors import filesystem_operation
from .links import file_link_result
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
                "Returns file metadata and an MCP resource link, never uploaded content. "
                f"Use resources/read for current content up to {services.read_max_bytes()} bytes; larger files require an HTTP download."
            ),
            parameters=UploadCommand.model_json_schema(),
            output_schema=CallerNodeSummary.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False,
            ),
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = UploadCommand.model_validate(arguments)
            content = command.content.decode()
        except ModelValidationError:
            raise
        except UnicodeError:
            raise invalid_content_error("utf-8") from None
        except ValueError:
            raise invalid_content_error("base64") from None
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
            operation_completed()
            node = (await self._services.access().enrich_nodes(caller, [result.node]))[0]
            return file_link_result(node, [node], "File uploaded successfully.\n" + node.model_dump_json(), self._services.read_max_bytes())
