import pytest
from fastmcp import Client

from umbod.core.callers import AuthenticationProvenance
from .conftest import FilesystemMcp, caller_snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("provenance", [
    AuthenticationProvenance.LOCAL_SIMULATION, AuthenticationProvenance.LOCAL_TEST,
])
async def test_mcp_keeps_strict_identity_denial_even_with_matching_explicit_grants(
    filesystem_mcp: FilesystemMcp, provenance: AuthenticationProvenance,
) -> None:
    filesystem_mcp.callers.current.set(caller_snapshot(
        "alice", "https://issuer", ("writers",), provenance,
    ))
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool("get_filesystem_root", {}, raise_on_error=False)
    assert result.is_error
    assert "filesystem_permission_denied" in result.content[0].text
