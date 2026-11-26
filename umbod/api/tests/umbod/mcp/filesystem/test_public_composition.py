from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from fastmcp import Client
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, InputRequiredResult

from tests.mcp_fixtures import build_test_mcp
from tests.support.system_settings import save_raw_settings
from umbod.config import AppConfig
from umbod.config.identity_policy import filesystem_managed_issuer
from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import MissingNode
from umbod.core.system_settings import UpdateSystemSettings, create_system_settings_service
from umbod.infrastructure import create_namespace_driver
from umbod.core.filesystem.browsing import FilesystemBrowsing
from umbod.core.filesystem.content import FilesystemContent
from umbod.core.filesystem.deletion import FilesystemDeletion
from umbod.core.filesystem.sharing import FilesystemSharing
from umbod.mcp.filesystem import CurrentFilesystemCallerCapture, DatabaseFilesystemServiceFactory
from umbod.core.filesystem.authorization.discovery import FilesystemOperation
from umbod.mcp.filesystem.discovery import FilesystemToolVisibility

from .conftest import caller_snapshot
from .test_browsing import create_node
from .test_tools import root_id


@pytest.mark.asyncio
@pytest.mark.parametrize("deployment,override,corrupt,requires_approval,mode", [
    (None, None, False, True, "auto"),
    (False, None, False, False, "auto"),
    (True, False, False, False, "auto"),
    (True, False, False, False, "legacy"),
    (False, True, False, True, "auto"),
    (False, None, True, True, "auto"),
])
async def test_public_delete_uses_effective_instance_approval_policy(
    monkeypatch: pytest.MonkeyPatch, deployment: bool | None, override: bool | None,
    corrupt: bool, requires_approval: bool, mode: str,
) -> None:
    settings = AppConfig()
    settings = settings.model_copy(update={"filesystem": settings.filesystem.model_copy(
        update={"require_mcp_file_deletion_approval": deployment},
    )})
    caller = caller_snapshot("alice", filesystem_managed_issuer(settings), (), AuthenticationProvenance.UPSTREAM_VERIFIED)
    monkeypatch.setattr(CurrentFilesystemCallerCapture, "capture", Mock(return_value=caller))
    monkeypatch.setattr(FilesystemToolVisibility, "capture", AsyncMock(return_value=frozenset(FilesystemOperation)))
    server = await build_test_mcp(settings, connector_registrations=[])
    database = server.persistence_runtime.database
    namespace = create_namespace_driver(database=database)
    try:
        if override is not None:
            await create_system_settings_service(database).set_settings(
                "administrator", UpdateSystemSettings(require_mcp_file_deletion_approval=override),
            )
        if corrupt:
            await save_raw_settings(database, {"require_mcp_file_deletion_approval": "false"})
        async with Client(server, mode=mode) as client:
            node_id = await create_node(client, await root_id(client), "approval-policy", "file")
            before = await namespace.get_node(UUID(node_id))
            stale = await client.call_tool("filesystem_delete_file", {
                "node_id": node_id, "expected_revision": before.revision + 1,
            }, raise_on_error=False)
            assert stale.is_error
            assert "filesystem_revision_conflict" in stale.content[0].text
            result = await client.session.call_tool("filesystem_delete_file", {
                "node_id": node_id, "expected_revision": before.revision,
            }, allow_input_required=True)
        if requires_approval:
            assert isinstance(result, InputRequiredResult)
            assert await namespace.get_node(UUID(node_id)) == before
        else:
            assert isinstance(result, CallToolResult)
            assert result.structured_content == {"node_id": node_id, "deleted": True}
            with pytest.raises(MissingNode):
                await namespace.get_node(UUID(node_id))
    finally:
        await server.persistence_runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["capture", "factory", "service"])
@pytest.mark.parametrize("tool,operation,method,arguments", [
    ("filesystem_share", "sharing", "share", {"node_id": "00000000-0000-0000-0000-000000000001", "group_id": "writers", "permissions": ["read"]}),
    ("filesystem_search_sharing_recipients", "sharing", "search_recipients", {"node_id": "00000000-0000-0000-0000-000000000001", "query": "writers"}),
    ("get_filesystem_node", "browsing", "get_node", {"node_id": "00000000-0000-0000-0000-000000000001"}),
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
