import asyncio
from typing import Any
from uuid import UUID

import anyio
from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError
from fastmcp.resources import Resource, ResourceTemplate
from fastmcp.resources.base import ResourceContent, ResourceResult
from pydantic import PrivateAttr
from mcp.types import ResourceTemplate as SDKResourceTemplate

from umbod.core.filesystem.content import ContentDownload
from umbod.core.filesystem.errors import StorageFailure
from umbod.core.filesystem.ports import ByteStream
from umbod.mcp.connectors.downstream_mcp.provider import _REQUEST_CONNECTOR_SCOPE

from .errors import FILESYSTEM_ACCESS_DENIED, InvalidReadEncoding, ReadTooLarge, filesystem_resource_operation
from .links import FILE_RESOURCE_TEMPLATE, file_resource_uri
from .ports import ClosableByteStream, FilesystemCallerCapture, FilesystemServiceFactory


MAX_READ_BYTES = 1_048_576


def ensure_resource_scope() -> None:
    if _REQUEST_CONNECTOR_SCOPE.get():
        raise ResourceError(FILESYSTEM_ACCESS_DENIED)


async def close_stream(stream: ByteStream) -> None:
    if isinstance(stream, ClosableByteStream):
        with anyio.CancelScope(shield=True):
            await stream.aclose()


async def bounded_content(download: ContentDownload) -> str | bytes:
    try:
        if download.size < 0:
            raise StorageFailure("Invalid stored content size")
        if download.size > MAX_READ_BYTES:
            raise ReadTooLarge()
        data = bytearray()
        async for chunk in download.data:
            if len(data) + len(chunk) > MAX_READ_BYTES:
                raise ReadTooLarge()
            data.extend(chunk)
        if len(data) != download.size:
            raise StorageFailure("Stored content size mismatch")
        result = resource_content(bytes(data), normalized_mime_type(download.node.metadata.content_type))
    except BaseException:
        try:
            await close_stream(download.data)
        except (Exception, asyncio.CancelledError):
            pass
        raise
    else:
        await close_stream(download.data)
        return result


def normalized_mime_type(value: object) -> str:
    if not isinstance(value, str):
        return "application/octet-stream"
    normalized = value.split(";", 1)[0].strip().lower()
    if "/" not in normalized or any(character.isspace() for character in normalized):
        return "application/octet-stream"
    return normalized


def resource_content(data: bytes, mime_type: str) -> str | bytes:
    if mime_type.startswith("text/") or mime_type in {"application/json", "application/xml"} or mime_type.endswith(("+json", "+xml")):
        try:
            return data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise InvalidReadEncoding() from None
    return data


class FilesystemFileResource(Resource):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()
    _node_id: UUID = PrivateAttr()

    def __init__(self, node_id: UUID, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(uri=file_resource_uri(node_id), name="filesystem_file", mime_type="application/octet-stream")
        self._node_id = node_id
        self._callers = callers
        self._services = services

    async def read(self) -> ResourceResult:
        ensure_resource_scope()
        with filesystem_resource_operation():
            caller = self._callers.capture()
            download = await self._services.content().open_download(caller, self._node_id)
            data = await bounded_content(download)
            mime_type = normalized_mime_type(download.node.metadata.content_type)
            return ResourceResult([ResourceContent(
                data, mime_type=mime_type,
                meta={"revision": download.node.revision, "size_bytes": download.size},
            )])


class FilesystemFileResourceTemplate(ResourceTemplate):
    _callers: FilesystemCallerCapture = PrivateAttr()
    _services: FilesystemServiceFactory = PrivateAttr()

    def __init__(self, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
        super().__init__(
            name="filesystem_file", uri_template=FILE_RESOURCE_TEMPLATE,
            description="Current authorized file content, complete reads up to 1 MiB.",
            mime_type="application/octet-stream",
            parameters={"type": "object", "properties": {"node_id": {"type": "string", "format": "uuid"}}, "required": ["node_id"]},
        )
        self._callers = callers
        self._services = services

    def to_mcp_template(self, **overrides: Any) -> SDKResourceTemplate:
        return super().to_mcp_template(**{**overrides, "mimeType": None})

    async def create_resource(self, uri: str, params: dict[str, Any]) -> Resource:
        ensure_resource_scope()
        try:
            node_id = UUID(params["node_id"])
            if uri != file_resource_uri(node_id):
                raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ResourceError("filesystem_invalid_read: Invalid file resource URI") from None
        return FilesystemFileResource(node_id, self._callers, self._services)


def register_filesystem_resources(mcp: FastMCP, callers: FilesystemCallerCapture, services: FilesystemServiceFactory) -> None:
    mcp.add_template(FilesystemFileResourceTemplate(callers, services))
