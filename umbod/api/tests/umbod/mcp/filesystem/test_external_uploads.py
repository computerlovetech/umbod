import hashlib
from uuid import UUID

import pytest
from fastmcp import Client, FastMCP

from umbod.core.filesystem.uploads.models import ExternalTransfer
from umbod.mcp.filesystem.factory import DatabaseFilesystemServiceFactory
from umbod.mcp.filesystem.upload import FilesystemUploadTool
from umbod.mcp.filesystem.upload_sessions import FilesystemBeginUploadTool, FilesystemCompleteUploadTool
from tests.umbod.core.filesystem.test_external_uploads import MemoryExternalContent

from .conftest import FilesystemState
from .test_tools import METADATA


@pytest.mark.asyncio
async def test_external_mcp_begin_needs_no_api_origin_and_inline_remains_internal(filesystem_state: FilesystemState) -> None:
    async def inspect_namespace() -> None:
        return None

    content = MemoryExternalContent(filesystem_state.content, inspect_namespace)
    services = DatabaseFilesystemServiceFactory(
        filesystem_state.database, content, 1024, "https://issuer", "invalid-api-origin", max_read_bytes=1_048_576)
    assert services.upload_sessions() is not services.upload_sessions()
    assert services.upload_sessions().supports_external_transfer
    server = FastMCP()
    server.add_tool(FilesystemBeginUploadTool(filesystem_state.callers, services))
    server.add_tool(FilesystemCompleteUploadTool(filesystem_state.callers, services))
    server.add_tool(FilesystemUploadTool(filesystem_state.callers, services))
    async with Client(server) as client:
        from umbod.core.filesystem.namespace import ROOT_ID

        begin = await client.call_tool("filesystem_begin_upload", {
            "parent_id": str(ROOT_ID), "name": "external", "metadata": METADATA,
            "size_bytes": 3, "expected_sha256": hashlib.sha256(b"abc").hexdigest(),
        })
        data = begin.structured_content
        assert data["transfer"]["url"].startswith("https://objects.example.test/")
        assert data["transfer"]["headers"] == {"Content-Type": "application/octet-stream", "If-None-Match": "*"}
        assert "whole URL" in data["transfer"]["instructions"]
        session = await services.upload_sessions().get(filesystem_state.callers.capture(), UUID(data["upload_id"]))
        assert isinstance(session.delegated_transfer, ExternalTransfer)
        content.objects[session.delegated_transfer.storage_key] = (b"abc", "application/octet-stream")
        complete = await client.call_tool("filesystem_complete_upload", {"upload_id": data["upload_id"]})
        retry = await client.call_tool("filesystem_complete_upload", {"upload_id": data["upload_id"]})
        assert complete.structured_content == retry.structured_content
        assert complete.structured_content["sha256"] == hashlib.sha256(b"abc").hexdigest()
        assert content.verifications == 1
        inline = await client.call_tool("filesystem_upload", {
            "parent_id": str(ROOT_ID), "name": "inline", "metadata": METADATA,
            "content": {"encoding": "utf-8", "text": "inline"},
        })
        assert inline.structured_content["name"] == "inline"
        assert len(content.preparations) == content.verifications == 1
