from unittest.mock import Mock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider

from umbod.core.callers import AuthenticationProvenance, UnavailableSubject
from umbod.core.filesystem.authorization import ResolvedIdentity, VerifiedIdentityResolver
from umbod.core.permissions import InMemoryGroupConnectorToolPermissions
from umbod.mcp.auth.local_test_auth import SingleTestUserOAuthProvider
from umbod.mcp.filesystem import (
    CurrentFilesystemCallerCapture,
    RuntimeFilesystemGroupClaimFields,
    StaticFilesystemGroupClaimFields,
    register_filesystem_tools,
)
from umbod.mcp.filesystem.ports import FilesystemCallerCapture
from umbod.mcp.tools import McpObservedToolRegistrar
from umbod.mcp.tools.invocation import McpToolInvocationObserver
from .conftest import FilesystemMcp


@pytest.fixture
def upstream_provider() -> GoogleProvider:
    return GoogleProvider(
        client_id="client", client_secret="secret", base_url="https://umbod.test",
        jwt_signing_key="filesystem-test-signing-key",
    )


def access_token() -> AccessToken:
    return AccessToken(
        token="accepted", client_id="client", scopes=[],
        claims={
            "iss": "https://issuer", "sub": " exact-subject ",
            "active": ["writers", "writers", 7], "fallback": ["wrong"],
        },
    )


@pytest.mark.asyncio
async def test_snapshot_reads_one_token_and_preserves_verified_issuer_subject_groups(
    monkeypatch: pytest.MonkeyPatch, upstream_provider: GoogleProvider,
) -> None:
    source = Mock(return_value=access_token())
    monkeypatch.setattr("umbod.mcp.filesystem.caller.get_access_token", source)
    state = InMemoryGroupConnectorToolPermissions(group_claim_fields=("active",))
    capture: FilesystemCallerCapture = CurrentFilesystemCallerCapture(
        FastMCP(auth=upstream_provider), RuntimeFilesystemGroupClaimFields(state)
    )
    snapshot = capture.capture()
    identity = await VerifiedIdentityResolver().resolve(snapshot)
    assert isinstance(identity, ResolvedIdentity)
    assert identity.user.issuer == "https://issuer"
    assert identity.user.id == " exact-subject "
    assert {group.id for group in identity.groups} == {"writers"}
    assert snapshot.caller.authentication == AuthenticationProvenance.UPSTREAM_VERIFIED
    source.assert_called_once_with()


def test_absent_runtime_state_uses_configured_claim(
    monkeypatch: pytest.MonkeyPatch, upstream_provider: GoogleProvider,
) -> None:
    monkeypatch.setattr("umbod.mcp.filesystem.caller.get_access_token", access_token)
    capture: FilesystemCallerCapture = CurrentFilesystemCallerCapture(
        FastMCP(auth=upstream_provider), StaticFilesystemGroupClaimFields("fallback")
    )
    assert capture.capture().groups.group_ids == ("wrong",)


def test_active_runtime_claim_fields_are_not_frozen_at_registration(
    monkeypatch: pytest.MonkeyPatch, upstream_provider: GoogleProvider,
) -> None:
    monkeypatch.setattr("umbod.mcp.filesystem.caller.get_access_token", access_token)
    state = InMemoryGroupConnectorToolPermissions(group_claim_fields=("active",))
    capture: FilesystemCallerCapture = CurrentFilesystemCallerCapture(
        FastMCP(auth=upstream_provider), RuntimeFilesystemGroupClaimFields(state)
    )
    state.group_claim_fields = ("fallback",)
    assert capture.capture().groups.group_ids == ("wrong",)


def test_no_token_is_explicitly_unavailable(
    monkeypatch: pytest.MonkeyPatch, upstream_provider: GoogleProvider,
) -> None:
    monkeypatch.setattr("umbod.mcp.filesystem.caller.get_access_token", lambda: None)
    capture: FilesystemCallerCapture = CurrentFilesystemCallerCapture(
        FastMCP(auth=upstream_provider), StaticFilesystemGroupClaimFields("fallback")
    )
    snapshot = capture.capture()
    assert snapshot.caller.authentication == AuthenticationProvenance.UNAVAILABLE
    assert isinstance(snapshot.caller.subject, UnavailableSubject)


@pytest.mark.parametrize("provider,expected", [
    (None, AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED),
    (object.__new__(SingleTestUserOAuthProvider), AuthenticationProvenance.LOCAL_TEST),
])
def test_claims_cannot_promote_unverified_provider(
    monkeypatch: pytest.MonkeyPatch, provider: object, expected: AuthenticationProvenance,
) -> None:
    server = FastMCP()
    server.auth = provider
    monkeypatch.setattr("umbod.mcp.filesystem.caller.get_access_token", access_token)
    capture: FilesystemCallerCapture = CurrentFilesystemCallerCapture(server, StaticFilesystemGroupClaimFields("active"))
    assert capture.capture().caller.authentication == expected


@pytest.mark.asyncio
async def test_each_tool_invocation_captures_exactly_one_current_token(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
    upstream_provider: GoogleProvider,
) -> None:
    token = access_token()
    token.claims["sub"] = "alice"
    source = Mock(return_value=token)
    monkeypatch.setattr("umbod.mcp.filesystem.caller.get_access_token", source)
    server = FastMCP(auth=upstream_provider)
    register_filesystem_tools(
        McpObservedToolRegistrar(server, McpToolInvocationObserver(Mock(), filesystem_mcp.metrics)),
        CurrentFilesystemCallerCapture(server, StaticFilesystemGroupClaimFields("active")),
        filesystem_mcp.services,
    )
    assert source.call_count == 0
    async with Client(server) as client:
        root = (await client.call_tool("get_filesystem_root", {})).data
        node = (await client.call_tool("create_filesystem_file", {
            "parent_id": str(root.id), "name": "empty",
            "metadata": {"content_type": {}, "attributes": {}},
        })).data
        await client.call_tool("get_filesystem_node", {"node_id": str(node.id)})
        await client.call_tool("list_filesystem_children", {"parent_id": str(root.id)})
        await client.call_tool("create_filesystem_directory", {
            "parent_id": str(root.id), "name": "directory",
            "metadata": {"content_type": {}, "attributes": {}},
        })
    assert source.call_count == 5
