import asyncio
import base64
import json
from typing import Any, Literal

import anyio

from fastmcp.exceptions import ValidationError
from fastmcp.tools.base import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import PrivateAttr

from umbod.core.filesystem.content import ContentDownload
from umbod.core.filesystem.errors import StorageFailure
from umbod.core.filesystem.ports import ByteStream

from .authorization import root_filesystem_tool_access
from .errors import InvalidReadEncoding, ReadTooLarge, filesystem_operation
from .ports import ClosableByteStream, FilesystemCallerCapture, FilesystemServiceFactory
from .read_models import Base64ReadContent, ReadContent, ReadFileCommand, ReadFileResult, Utf8ReadContent


async def close_stream(stream: ByteStream) -> None:
    if isinstance(stream, ClosableByteStream):
        with anyio.CancelScope(shield=True):
            await stream.aclose()


async def bounded_content(
    download: ContentDownload, max_bytes: int, encoding: Literal["utf-8", "base64"],
) -> ReadContent:
    try:
        if download.size < 0:
            raise StorageFailure("Invalid stored content size")
        if download.size > max_bytes:
            raise ReadTooLarge()
        data = bytearray()
        async for chunk in download.data:
            if len(data) + len(chunk) > max_bytes:
                raise ReadTooLarge()
            data.extend(chunk)
        if len(data) != download.size:
            raise StorageFailure("Stored content size mismatch")
        content = encode_content(bytes(data), encoding)
    except BaseException:
        try:
            await close_stream(download.data)
        except (Exception, asyncio.CancelledError):
            pass
        raise
    else:
        await close_stream(download.data)
        return content


def encode_content(data: bytes, encoding: Literal["utf-8", "base64"]) -> ReadContent:
    if encoding == "base64":
        return Base64ReadContent(encoding="base64", data=base64.b64encode(data).decode("ascii"))
    try:
        return Utf8ReadContent(encoding="utf-8", text=data.decode("utf-8", errors="strict"))
    except UnicodeDecodeError:
        raise InvalidReadEncoding() from None


class FilesystemReadFileTool(Tool):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_read_file",
            description=(
                "Read one authorized file completely as strict UTF-8 text or canonical padded base64. "
                "Requires a UUID, encoding and explicit max_bytes budget, at most 1048576 raw bytes (1 MiB). "
                "Oversize files fail without partial content or silent truncation. "
                "Invalid UTF-8 fails; request base64 for binary files. Directories are unsupported. "
                "Returns the file revision captured when the read was authorized."
            ),
            parameters=ReadFileCommand.model_json_schema(),
            output_schema=ReadFileResult.model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
            ),
            auth=root_filesystem_tool_access,
        )
        self._callers = callers
        self._services = services

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            command = ReadFileCommand.model_validate_json(json.dumps(arguments, allow_nan=False))
        except (TypeError, ValueError):
            raise ValidationError("filesystem_invalid_read: Invalid file read arguments") from None
        with filesystem_operation():
            caller = self._callers.capture()
            download = await self._services.content().open_download(caller, command.node_id)
            content = await bounded_content(download, command.max_bytes, command.encoding)
            result = ReadFileResult(
                node_id=download.node.id, revision=download.node.revision, size_bytes=download.size,
                content=content,
            )
            return ToolResult(structured_content=result.model_dump(mode="json"))
