import base64
import json
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastmcp import Client
from fastmcp.client.client import CallToolResult
from jsonschema import validate

from umbod.core.callers import (
    AuthenticationProvenance, CallerContext, CallerSnapshot, GroupMembership, UnavailableSubject,
)
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.content import FilesystemContent
from umbod.core.filesystem.models import StorageKey
from umbod.core.filesystem.ports import ByteStream
from umbod.infrastructure import create_access_control_driver, create_namespace_driver
from umbod.mcp.connectors.downstream_mcp.provider import reset_request_connector_scope, set_request_connector_scope
from umbod.mcp.filesystem import DatabaseFilesystemServiceFactory
from umbod.mcp.filesystem.ports import FilesystemCallerCapture, FilesystemServiceFactory
from umbod.mcp.filesystem.read import FilesystemReadFileTool

from .conftest import FilesystemMcp, caller_snapshot
from .test_browsing import create_node
from .test_tools import root_id
from .test_upload import upload

TOOL = "filesystem_read_file"
CAP = 1_048_576
DENIED = "filesystem_permission_denied: Filesystem access denied"


async def read_file(client: Client, node_id: str, encoding: str, max_bytes: int) -> CallToolResult:
    return await client.call_tool(TOOL, {
        "node_id": node_id, "encoding": encoding, "max_bytes": max_bytes,
    }, raise_on_error=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,encoding", [
    ("Hej 世界 🌍".encode(), "utf-8"),
    (b"\x00\xff\xfe\x00", "base64"),
    (b"", "utf-8"),
    (b"", "base64"),
    (b"x" * CAP, "utf-8"),
    (b"x" * CAP, "base64"),
], ids=["unicode", "binary", "empty-text", "empty-base64", "text-cap", "binary-cap"])
async def test_read_roundtrips_structured_and_text_only_content(
    filesystem_mcp: FilesystemMcp, payload: bytes, encoding: str,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        published = await upload(client, await root_id(client), {
            "encoding": "base64", "data": base64.b64encode(payload).decode(),
        })
        captures = filesystem_mcp.callers.count
        result = await read_file(client, published.structured_content["id"], encoding, len(payload))
        descriptor = next(tool for tool in await client.list_tools() if tool.name == TOOL)
    expected_content = {"encoding": "utf-8", "text": payload.decode()} if encoding == "utf-8" else {
        "encoding": "base64", "data": base64.b64encode(payload).decode(),
    }
    assert not result.is_error
    assert result.structured_content == {
        "node_id": published.structured_content["id"], "revision": published.structured_content["revision"],
        "size_bytes": len(payload), "content": expected_content,
    }
    assert json.loads(result.content[0].text) == result.structured_content
    validate(result.structured_content, descriptor.output_schema)
    assert filesystem_mcp.callers.count == captures + 1
    assert any(sample.labels["tool_name"] == TOOL and sample.labels["outcome"] == "success"
               for sample in filesystem_mcp.metrics.metric_samples())


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding", ["utf-8", "base64"])
async def test_created_empty_file_reads_without_stored_content(filesystem_mcp: FilesystemMcp, encoding: str) -> None:
    async with Client(filesystem_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "empty", "file")
        result = await read_file(client, node_id, encoding, 0)
    assert not result.is_error
    assert result.structured_content == {
        "node_id": node_id, "revision": 1, "size_bytes": 0,
        "content": {"encoding": encoding, "text" if encoding == "utf-8" else "data": ""},
    }
    assert filesystem_mcp.content.put_count == 0


@pytest.mark.asyncio
async def test_invalid_utf8_has_safe_error_and_base64_remains_readable(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        published = await upload(client, await root_id(client), {"encoding": "base64", "data": "/w=="})
        result = await read_file(client, published.structured_content["id"], "utf-8", CAP)
        binary = await read_file(client, published.structured_content["id"], "base64", CAP)
    assert result.is_error
    assert result.content[0].text == "filesystem_read_invalid_encoding: File is not valid UTF-8; use base64"
    assert binary.structured_content["content"] == {"encoding": "base64", "data": "/w=="}
    assert any(sample.labels["tool_name"] == TOOL and sample.labels["outcome"] == "failure"
               for sample in filesystem_mcp.metrics.metric_samples())


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [
    {},
    {"encoding": "utf-8", "max_bytes": CAP},
    {"node_id": str(uuid4()), "max_bytes": CAP},
    {"node_id": str(uuid4()), "encoding": "utf-8"},
    {"node_id": "invalid", "encoding": "utf-8", "max_bytes": CAP},
    {"node_id": str(uuid4()), "encoding": "UTF-8", "max_bytes": CAP},
    *[{"node_id": str(uuid4()), "encoding": "utf-8", "max_bytes": value}
      for value in (True, False, 1.0, "1", -1, CAP + 1, None)],
    *[{"node_id": str(uuid4()), "encoding": "utf-8", "max_bytes": CAP, field: "SECRET"}
      for field in ("caller", "owner", "identity", "groups", "grants", "storage_key", "content")],
])
async def test_read_rejects_invalid_arguments_before_capture(
    filesystem_mcp: FilesystemMcp, arguments: dict[str, Any],
) -> None:
    captures = filesystem_mcp.callers.count
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool(TOOL, arguments, raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == "filesystem_invalid_read: Invalid file read arguments"
    assert filesystem_mcp.callers.count == captures


@pytest.mark.asyncio
async def test_read_schema_advertises_required_bounded_arguments_and_annotations(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        descriptor = next(tool for tool in await client.list_tools() if tool.name == TOOL)
    schema = descriptor.input_schema
    assert set(schema["properties"]) == set(schema["required"]) == {"node_id", "encoding", "max_bytes"}
    assert schema["additionalProperties"] is False
    assert schema["properties"]["node_id"]["format"] == "uuid"
    assert schema["properties"]["encoding"]["enum"] == ["utf-8", "base64"]
    assert schema["properties"]["max_bytes"]["type"] == "integer"
    assert schema["properties"]["max_bytes"]["minimum"] == 0
    assert schema["properties"]["max_bytes"]["maximum"] == CAP
    assert set(descriptor.output_schema["properties"]) == {"node_id", "revision", "size_bytes", "content"}
    assert descriptor.annotations.read_only_hint is True
    assert descriptor.annotations.destructive_hint is False
    assert descriptor.annotations.idempotent_hint is True
    assert descriptor.annotations.open_world_hint is False


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer,provenance", [
    ("https://other", AuthenticationProvenance.UPSTREAM_VERIFIED),
    ("https://issuer", AuthenticationProvenance.LOCAL_TEST),
    ("https://issuer", AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED),
    ("https://issuer", AuthenticationProvenance.LOCAL_SIMULATION),
    ("https://issuer", AuthenticationProvenance.LOCAL_SEMANTIC),
])
async def test_read_rejects_untrusted_identity(
    filesystem_mcp: FilesystemMcp, issuer: str, provenance: AuthenticationProvenance,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
        filesystem_mcp.callers.current.set(caller_snapshot("alice", issuer, ("writers",), provenance))
        result = await read_file(client, node_id, "utf-8", CAP)
    assert result.is_error
    assert result.content[0].text == DENIED


@pytest.mark.asyncio
async def test_read_without_authentication_is_denied(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
        filesystem_mcp.callers.current.set(CallerSnapshot(
            caller=CallerContext(authentication=AuthenticationProvenance.UNAVAILABLE,
                                 subject=UnavailableSubject(kind="unavailable")),
            groups=GroupMembership(group_ids=()),
        ))
        result = await read_file(client, node_id, "utf-8", CAP)
    assert result.is_error
    assert result.content[0].text == DENIED


@pytest.mark.asyncio
async def test_missing_and_unauthorized_reads_have_identical_errors(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        node_id = await create_node(client, await root_id(client), "private", "file")
        filesystem_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        denied = await read_file(client, node_id, "utf-8", CAP)
        missing = await read_file(client, str(uuid4()), "utf-8", CAP)
    assert denied.is_error and missing.is_error
    assert denied.content == missing.content
    assert denied.content[0].text == DENIED


@pytest.mark.asyncio
async def test_direct_read_grant_needs_no_ancestor_access_and_revocation_is_fresh(filesystem_mcp: FilesystemMcp) -> None:
    policies = create_access_control_driver(database=filesystem_mcp.database)
    principal = Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob")
    async with Client(filesystem_mcp.server) as client:
        directory = await create_node(client, await root_id(client), "private", "directory")
        published = await upload(client, directory, {"encoding": "utf-8", "text": "shared"})
        node_id = published.structured_content["id"]
        await policies.add_grant(AccessGrant(
            node_id=UUID(node_id), principal=principal, permissions={Permission.DISCOVER, Permission.READ}, recursive=False,
        ))
        filesystem_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", (), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        parent = await client.call_tool("get_filesystem_node", {"node_id": directory}, raise_on_error=False)
        allowed = await read_file(client, node_id, "utf-8", CAP)
        await policies.remove_grant(UUID(node_id), principal)
        revoked = await read_file(client, node_id, "utf-8", CAP)
    assert parent.is_error
    assert allowed.structured_content["content"] == {"encoding": "utf-8", "text": "shared"}
    assert revoked.is_error
    assert revoked.content[0].text == DENIED


@pytest.mark.asyncio
async def test_connector_scope_hides_read_and_denies_invocation_before_capture(filesystem_mcp: FilesystemMcp) -> None:
    captures = filesystem_mcp.callers.count
    token = set_request_connector_scope("connector-only")
    try:
        async with Client(filesystem_mcp.server) as client:
            descriptors = await client.list_tools()
            result = await read_file(client, str(uuid4()), "utf-8", CAP)
        assert TOOL not in {tool.name for tool in descriptors}
        assert result.is_error
        assert filesystem_mcp.callers.count == captures
    finally:
        reset_request_connector_scope(token)
    async with Client(filesystem_mcp.server) as client:
        assert TOOL in {tool.name for tool in await client.list_tools()}


@pytest.mark.asyncio
async def test_each_read_captures_once_opens_once_and_creates_fresh_service(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        node_id = UUID(await create_node(client, await root_id(client), "empty", "file"))
    caller = filesystem_mcp.callers.current.get()
    callers = Mock(spec=FilesystemCallerCapture)
    callers.capture.return_value = caller
    services = [Mock(spec=FilesystemContent), Mock(spec=FilesystemContent)]
    for service in services:
        service.open_download = AsyncMock(side_effect=filesystem_mcp.files.open_download)
    factory = Mock(spec=FilesystemServiceFactory)
    factory.content.side_effect = services
    tool = FilesystemReadFileTool(callers, factory)
    for _ in services:
        await tool.run({"node_id": str(node_id), "encoding": "utf-8", "max_bytes": CAP})
    assert callers.capture.call_count == 2
    assert factory.content.call_count == 2
    factory.browsing.assert_not_called()
    for service in services:
        service.open_download.assert_awaited_once_with(caller, node_id)


@pytest.mark.asyncio
async def test_read_cap_is_independent_of_configured_upload_limit(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        published = await upload(client, await root_id(client), {"encoding": "utf-8", "text": "readable"})
    factory = DatabaseFilesystemServiceFactory(filesystem_mcp.database, filesystem_mcp.content, 0, "https://issuer")
    first = factory.content()
    assert first is not factory.content()
    result = await FilesystemReadFileTool(filesystem_mcp.callers, factory).run({
        "node_id": published.structured_content["id"], "encoding": "utf-8", "max_bytes": CAP,
    })
    assert result.structured_content["content"] == {"encoding": "utf-8", "text": "readable"}


@pytest.mark.asyncio
async def test_read_preserves_captured_revision_and_bytes_during_namespace_update(
    filesystem_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = create_namespace_driver(database=filesystem_mcp.database)
    async with Client(filesystem_mcp.server) as client:
        published = await upload(client, await root_id(client), {"encoding": "utf-8", "text": "original"})
        node_id = UUID(published.structured_content["id"])
        replacement = await upload(client, await create_node(client, await root_id(client), "other", "directory"), {
            "encoding": "utf-8", "text": "replacement",
        })
        replacement_node = await namespace.get_node(UUID(replacement.structured_content["id"]))
        original_get = filesystem_mcp.content.get

        async def update_then_stream(key: StorageKey) -> ByteStream:
            await namespace.update_node(node_id, content=replacement_node.content,
                                        expected_revision=published.structured_content["revision"])
            async for chunk in original_get(key):
                yield chunk

        monkeypatch.setattr(filesystem_mcp.content, "get", update_then_stream)
        result = await read_file(client, str(node_id), "utf-8", CAP)
    assert result.structured_content == {
        "node_id": str(node_id), "revision": published.structured_content["revision"], "size_bytes": 8,
        "content": {"encoding": "utf-8", "text": "original"},
    }
    assert (await namespace.get_node(node_id)).revision == published.structured_content["revision"] + 1
