import pytest
from fastmcp import Client, FastMCP

from umbod.core.callers import AuthenticationProvenance
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.infrastructure import InMemoryContentConfig, create_access_control_driver, create_content_driver, create_filesystem_homes
from umbod.mcp.filesystem.browsing import FilesystemBrowseTool
from umbod.mcp.filesystem.factory import DatabaseFilesystemServiceFactory
from umbod.mcp.filesystem.update import FilesystemUpdateNodeTool
from tests.persistence_runtime import prepared_inmemory_runtime
from tests.support.filesystem.access_snapshots import fail_stored_grant_decoding
from .conftest import ScopedCallerCapture, caller_snapshot


@pytest.mark.asyncio
async def test_undecodable_policy_browse_and_update_return_unavailable_not_private(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = await prepared_inmemory_runtime()
    try:
        database = runtime.database
        callers = ScopedCallerCapture()
        callers.current.set(caller_snapshot("alice", "issuer", (), AuthenticationProvenance.UPSTREAM_VERIFIED))
        home = await create_filesystem_homes(database=database).get_or_provision(callers.current.get())
        grant = AccessGrant(
            node_id=home.id, principal=Principal(type=PrincipalType.USER, issuer="issuer", id="bob"),
            permissions={Permission.DISCOVER, Permission.WRITE}, recursive=False,
        )
        await create_access_control_driver(database=database).add_grant(grant)
        fail_stored_grant_decoding(database, home.id, monkeypatch)
        services = DatabaseFilesystemServiceFactory(
            database, create_content_driver(InMemoryContentConfig(type="inmemory")), 1024, "issuer", "http://localhost",
        )
        server = FastMCP()
        server.add_tool(FilesystemBrowseTool(callers, services))
        server.add_tool(FilesystemUpdateNodeTool(callers, services))
        async with Client(server) as client:
            inspected = await client.call_tool("filesystem_browse", {
                "operation": "stat", "target": {"type": "node", "node_id": str(home.id)},
            })
            node = inspected.structured_content["result"]["node"]
            assert node["permissions"]["can_write"] is True and node["permissions"]["can_share"] is True
            assert node["visible_to"] == {"type": "unavailable"}
            assert node["sharing"] == {"can_share": False}
            assert 'visible_to={"type":"unavailable"}' in inspected.content[0].text
            assert "sharing unavailable" in inspected.content[0].text
            assert "not permitted" not in inspected.content[0].text
            assert "no manageable direct grants" not in inspected.content[0].text
            updated = await client.call_tool("update_filesystem_node", {
                "node_id": str(home.id), "name": "renamed", "expected_revision": home.revision,
            })
            assert updated.structured_content["name"] == "renamed"
            assert updated.structured_content["revision"] == home.revision + 1
            assert updated.structured_content["visible_to"] == {"type": "unavailable"}
            assert updated.structured_content["sharing"] == {"can_share": False}
            assert updated.structured_content["permissions"]["can_write"] is True
    finally:
        await runtime.shutdown()
