from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import Client, FastMCP

from umbod.core.filesystem.uploads import UploadService
from umbod.mcp.filesystem import DatabaseFilesystemServiceFactory, register_filesystem_tools
from umbod.mcp.filesystem.ports import FilesystemServiceFactory
from umbod.mcp.listeners import create_mcp_signals
from umbod.mcp.signals import McpInvocationPublisher
from umbod.mcp.tools import McpObservedToolRegistrar

from .conftest import FilesystemMcp
from .test_tools import root_id
from .test_upload import CAP, upload


def server_for(filesystem: FilesystemMcp, services: FilesystemServiceFactory) -> FastMCP:
    server = FastMCP()
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(
            create_mcp_signals(Mock(), filesystem.metrics, Mock()),
        )),
        filesystem.callers, services,
    )
    return server


@pytest.mark.asyncio
async def test_lower_configured_limit_rejects_without_storage(filesystem_mcp: FilesystemMcp) -> None:
    services = DatabaseFilesystemServiceFactory(filesystem_mcp.database, filesystem_mcp.content, 3, "https://issuer")
    async with Client(server_for(filesystem_mcp, services)) as client:
        result = await upload(client, await root_id(client), {"encoding": "utf-8", "text": "four"})
    assert result.is_error
    assert result.content[0].text == "filesystem_upload_too_large: Filesystem upload too large"
    assert filesystem_mcp.content.put_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["capture", "factory", "begin", "put", "complete"])
async def test_upload_sanitizes_failures_at_every_stage(
    filesystem_mcp: FilesystemMcp, stage: str,
) -> None:
    services = Mock(spec=FilesystemServiceFactory, wraps=filesystem_mcp.services)
    uploads = Mock(spec=UploadService, wraps=filesystem_mcp.services.uploads())
    services.uploads.return_value = uploads
    failure = RuntimeError("SECRET content /private/storage")
    if stage == "capture":
        callers = Mock(wraps=filesystem_mcp.callers)
        callers.capture.side_effect = failure
    else:
        callers = filesystem_mcp.callers
    if stage == "factory":
        services.uploads.side_effect = failure
    elif stage in {"begin", "put", "complete"}:
        setattr(uploads, stage, AsyncMock(side_effect=failure))
    server = FastMCP()
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpInvocationPublisher(
            create_mcp_signals(Mock(), filesystem_mcp.metrics, Mock()),
        )), callers, services,
    )
    async with Client(filesystem_mcp.server) as client:
        parent = await root_id(client)
    async with Client(server) as client:
        result = await upload(client, parent, {"encoding": "utf-8", "text": "SECRET"})
    assert result.is_error
    assert result.content[0].text == "filesystem_operation_failed: Filesystem operation failed"


@pytest.mark.asyncio
async def test_decoded_cap_is_checked_before_constructing_upload_service(filesystem_mcp: FilesystemMcp) -> None:
    services = Mock(spec=FilesystemServiceFactory, wraps=filesystem_mcp.services)
    services.uploads.side_effect = AssertionError("Upload service must not be used")
    async with Client(server_for(filesystem_mcp, services)) as client:
        result = await upload(client, await root_id(client), {"encoding": "utf-8", "text": "é" * CAP})
    assert result.is_error
    assert result.content[0].text == "filesystem_upload_too_large: Filesystem upload too large"
    services.uploads.assert_not_called()
    assert filesystem_mcp.content.put_count == 0
