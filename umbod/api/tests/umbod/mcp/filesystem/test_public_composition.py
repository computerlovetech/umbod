from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import Client

from tests.mcp_fixtures import build_test_mcp
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.content import FilesystemContent
from umbod.core.filesystem.deletion import FilesystemDeletion
from umbod.mcp.filesystem import CurrentFilesystemCallerCapture, DatabaseFilesystemServiceFactory


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["capture", "factory", "service"])
@pytest.mark.parametrize("tool,operation,method,arguments", [
    ("get_filesystem_root", "browsing", "get_root", {}),
    ("filesystem_delete_file", "deletion", "delete_file", {
        "node_id": "00000000-0000-0000-0000-000000000001", "expected_revision": 1,
    }),
    ("filesystem_read_file", "content", "open_download", {
        "node_id": "00000000-0000-0000-0000-000000000001", "encoding": "utf-8", "max_bytes": 1_048_576,
    }),
])
async def test_public_composition_sanitizes_unexpected_filesystem_failures(
    monkeypatch: pytest.MonkeyPatch, stage: str, tool: str, operation: str,
    method: str, arguments: dict[str, Any],
) -> None:
    failure = RuntimeError("SECRET backend /private/path")
    server = await build_test_mcp(connector_registrations=[])
    if stage == "capture":
        monkeypatch.setattr(CurrentFilesystemCallerCapture, "capture", Mock(side_effect=failure))
    elif stage == "factory":
        monkeypatch.setattr(DatabaseFilesystemServiceFactory, operation, Mock(side_effect=failure))
    else:
        service = Mock(spec={
            "browsing": FilesystemBrowsing, "deletion": FilesystemDeletion, "content": FilesystemContent,
        }[operation])
        setattr(service, method, AsyncMock(side_effect=failure))
        monkeypatch.setattr(DatabaseFilesystemServiceFactory, operation, Mock(return_value=service))
    try:
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments, raise_on_error=False)
        assert result.is_error
        assert result.content[0].text == "filesystem_operation_failed: Filesystem operation failed"
        assert "SECRET" not in result.content[0].text
        assert "/private/path" not in result.content[0].text
    finally:
        await server.persistence_runtime.shutdown()
