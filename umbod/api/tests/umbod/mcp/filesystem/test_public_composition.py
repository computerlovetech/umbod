from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import Client

from tests.mcp_fixtures import build_test_mcp
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.mcp.filesystem import CurrentFilesystemCallerCapture, DatabaseFilesystemServiceFactory


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["capture", "factory", "service"])
async def test_public_composition_sanitizes_unexpected_filesystem_failures(
    monkeypatch: pytest.MonkeyPatch, stage: str,
) -> None:
    failure = RuntimeError("SECRET backend /private/path")
    server = await build_test_mcp(connector_registrations=[])
    if stage == "capture":
        monkeypatch.setattr(CurrentFilesystemCallerCapture, "capture", Mock(side_effect=failure))
    elif stage == "factory":
        monkeypatch.setattr(DatabaseFilesystemServiceFactory, "browsing", Mock(side_effect=failure))
    else:
        browsing = Mock(spec=FilesystemBrowsing)
        browsing.get_root = AsyncMock(side_effect=failure)
        monkeypatch.setattr(DatabaseFilesystemServiceFactory, "browsing", Mock(return_value=browsing))
    try:
        async with Client(server) as client:
            result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)
        assert result.is_error
        assert result.content[0].text == "filesystem_operation_failed: Filesystem operation failed"
        assert "SECRET" not in result.content[0].text
        assert "/private/path" not in result.content[0].text
    finally:
        await server.persistence_runtime.shutdown()
