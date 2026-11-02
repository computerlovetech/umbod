from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import Client
from mcp.shared.exceptions import MCPError

from tests.mcp_fixtures import build_test_mcp
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.content import FilesystemContent
from umbod.core.filesystem.deletion import FilesystemDeletion
from umbod.core.filesystem.sharing import FilesystemSharing
from umbod.mcp.filesystem import CurrentFilesystemCallerCapture, DatabaseFilesystemServiceFactory
from umbod.core.filesystem.authorization.discovery import FilesystemOperation
from umbod.mcp.filesystem.authorization import FilesystemToolVisibility


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["capture", "factory", "service"])
@pytest.mark.parametrize("tool,operation,method,arguments", [
    ("filesystem_search_sharing_recipients", "sharing", "search_recipients", {
        "node_id": "00000000-0000-0000-0000-000000000001", "query": "Observed",
    }),
    ("filesystem_share", "sharing", "share", {
        "node_id": "00000000-0000-0000-0000-000000000001", "group_id": "writers", "permissions": ["read"],
    }),
    ("filesystem_share", "sharing", "share", {
        "node_id": "00000000-0000-0000-0000-000000000001",
        "recipient": {"type": "user", "user_id": "observed-user"}, "permissions": ["read"],
    }),
    ("get_filesystem_root", "browsing", "get_root", {}),
    ("filesystem_delete_file", "deletion", "check_delete_eligibility", {
        "node_id": "00000000-0000-0000-0000-000000000001", "expected_revision": 1,
    }),
])
async def test_public_composition_sanitizes_unexpected_filesystem_failures(
    monkeypatch: pytest.MonkeyPatch, stage: str, tool: str, operation: str,
    method: str, arguments: dict[str, Any],
) -> None:
    failure = RuntimeError("SECRET backend /private/path")
    server = await build_test_mcp(connector_registrations=[])
    monkeypatch.setattr(FilesystemToolVisibility, "capture", AsyncMock(return_value=frozenset(FilesystemOperation)))
    if stage == "capture":
        monkeypatch.setattr(CurrentFilesystemCallerCapture, "capture", Mock(side_effect=failure))
    elif stage == "factory":
        monkeypatch.setattr(DatabaseFilesystemServiceFactory, operation, Mock(side_effect=failure))
    else:
        service = Mock(spec={
            "browsing": FilesystemBrowsing, "deletion": FilesystemDeletion, "content": FilesystemContent,
            "sharing": FilesystemSharing,
        }[operation])
        setattr(service, method, AsyncMock(side_effect=failure))
        monkeypatch.setattr(DatabaseFilesystemServiceFactory, operation, Mock(return_value=service))
    try:
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments, raise_on_error=False)
        assert result.is_error
        assert result.content[0].text == "filesystem_operation_failed: Filesystem operation failed."
        assert "SECRET" not in result.content[0].text
        assert "/private/path" not in result.content[0].text
    finally:
        await server.persistence_runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["capture", "factory", "service"])
async def test_public_resource_composition_sanitizes_every_read_stage(
    monkeypatch: pytest.MonkeyPatch, stage: str,
) -> None:
    server = await build_test_mcp(connector_registrations=[])
    failure = RuntimeError("SECRET backend /private/path")
    if stage == "capture":
        monkeypatch.setattr(CurrentFilesystemCallerCapture, "capture", Mock(side_effect=failure))
    elif stage == "factory":
        monkeypatch.setattr(DatabaseFilesystemServiceFactory, "content", Mock(side_effect=failure))
    else:
        service = Mock(spec=FilesystemContent)
        service.open_download = AsyncMock(side_effect=failure)
        monkeypatch.setattr(DatabaseFilesystemServiceFactory, "content", Mock(return_value=service))
    try:
        async with Client(server) as client:
            with pytest.raises(MCPError, match="filesystem_operation_failed: Filesystem operation failed.") as error:
                await client.read_resource("umbod://filesystem/files/00000000-0000-0000-0000-000000000001")
        assert "SECRET" not in str(error.value)
        assert "/private/path" not in str(error.value)
    finally:
        await server.persistence_runtime.shutdown()
