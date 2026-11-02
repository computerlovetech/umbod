import asyncio
import base64
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastmcp import Client
from fastmcp.exceptions import ResourceError
from mcp.shared.exceptions import MCPError
from mcp.types import BlobResourceContents, TextResourceContents

from umbod.core.callers import AuthenticationProvenance, CallerContext, CallerSnapshot, GroupMembership, UnavailableSubject
from umbod.core.filesystem import AccessGrant, Permission, Principal, PrincipalType
from umbod.core.filesystem.content import FilesystemContent
from umbod.infrastructure import create_access_control_driver, create_namespace_driver
from umbod.core.filesystem.models import StorageKey
from umbod.core.filesystem.ports import ByteStream
from umbod.mcp.filesystem import DatabaseFilesystemServiceFactory
from umbod.mcp.connectors.downstream_mcp.provider import reset_request_connector_scope, set_request_connector_scope
from umbod.mcp.filesystem.links import FILE_RESOURCE_TEMPLATE, file_resource_uri
from umbod.mcp.filesystem.ports import FilesystemServiceFactory
from umbod.mcp.filesystem.resources import FilesystemFileResource, FilesystemFileResourceTemplate, MAX_READ_BYTES

from .conftest import FilesystemMcp, caller_snapshot
from .test_browsing import create_node
from .test_tools import root_id


DENIED = "filesystem_permission_denied: Filesystem access denied. Choose an accessible node or ask its owner for the required permissions. Creating files requires discover and write on the parent directory; filesystem_browse with operation home resolves your private upload destination."


async def publish(client: Client, payload: bytes, mime_type: object) -> dict[str, object]:
    result = await client.call_tool("filesystem_upload", {
        "parent_id": await root_id(client), "name": str(uuid4()),
        "metadata": {"content_type": mime_type, "attributes": {}},
        "content": {"encoding": "base64", "data": base64.b64encode(payload).decode()},
    })
    return result.structured_content


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,mime_type,textual,expected_mime", [
    ("Hej 世界 🌍".encode(), " Text/Plain ; charset=utf-8", True, "text/plain"),
    (b"{}", "application/json", True, "application/json"),
    (b"{}", "application/problem+json", True, "application/problem+json"),
    (b"<a/>", "application/xml", True, "application/xml"),
    (b"<a/>", "image/svg+xml", True, "image/svg+xml"),
    (b"\x00\xff", "image/png", False, "image/png"),
    (b"\xff", {}, False, "application/octet-stream"),
    (b"", "text/plain", True, "text/plain"),
    (b"x" * MAX_READ_BYTES, "application/octet-stream", False, "application/octet-stream"),
])
async def test_resource_roundtrips_content_and_revision_metadata(
    filesystem_invocation_mcp: FilesystemMcp, payload: bytes, mime_type: object,
    textual: bool, expected_mime: str,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        published = await publish(client, payload, mime_type)
        captures = filesystem_invocation_mcp.callers.count
        result = await client.read_resource(file_resource_uri(UUID(published["id"])))
    content = result[0]
    assert content.mime_type == expected_mime
    assert content.meta == {"revision": published["revision"], "size_bytes": len(payload)}
    if textual:
        assert isinstance(content, TextResourceContents)
        assert content.text == payload.decode()
    else:
        assert isinstance(content, BlobResourceContents)
        assert base64.b64decode(content.blob) == payload
    assert filesystem_invocation_mcp.callers.count == captures + 1


@pytest.mark.asyncio
async def test_template_only_no_read_tool_or_file_enumeration(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        await publish(client, b"hello", "text/plain")
        await filesystem_mcp.runtime.reconcile()
        templates = await client.list_resource_templates()
        assert [str(template.uri_template) for template in templates] == [FILE_RESOURCE_TEMPLATE]
        assert templates[0].mime_type is None
        assert await client.list_resources() == []
        assert "filesystem_read_file" not in {tool.name for tool in await client.list_tools()}


@pytest.mark.asyncio
async def test_invalid_text_has_safe_resource_error(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        published = await publish(client, b"\xffSECRET", "text/plain")
        with pytest.raises(MCPError, match="filesystem_read_invalid_encoding: File is not valid UTF-8. Use an authorized HTTP download to retrieve the original bytes.") as error:
            await client.read_resource(file_resource_uri(UUID(published["id"])))
    assert "base64" not in str(error.value)
    assert "SECRET" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer,provenance", [
    ("https://other", AuthenticationProvenance.UPSTREAM_VERIFIED),
    ("https://issuer", AuthenticationProvenance.LOCAL_TEST),
    ("https://issuer", AuthenticationProvenance.DEPLOYMENT_AUTHENTICATED),
    ("https://issuer", AuthenticationProvenance.UNAVAILABLE),
])
async def test_untrusted_identity_is_denied(
    filesystem_invocation_mcp: FilesystemMcp, issuer: str, provenance: AuthenticationProvenance,
) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        published = await publish(client, b"secret", "text/plain")
        snapshot = CallerSnapshot(
            caller=CallerContext(authentication=provenance, subject=UnavailableSubject(kind="unavailable")),
            groups=GroupMembership(group_ids=()),
        ) if provenance == AuthenticationProvenance.UNAVAILABLE else caller_snapshot("alice", issuer, ("writers",), provenance)
        filesystem_invocation_mcp.callers.current.set(snapshot)
        with pytest.raises(MCPError, match=DENIED):
            await client.read_resource(file_resource_uri(UUID(published["id"])))


@pytest.mark.asyncio
async def test_missing_and_denied_are_indistinguishable(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        published = await publish(client, b"secret", "text/plain")
        filesystem_invocation_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", (), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        messages: list[str] = []
        for node_id in (UUID(published["id"]), uuid4()):
            with pytest.raises(MCPError, match=DENIED) as error:
                await client.read_resource(file_resource_uri(node_id))
            messages.append(str(error.value))
    assert messages[0] == messages[1]


@pytest.mark.asyncio
async def test_direct_grant_and_retained_resource_revocation_are_fresh(filesystem_invocation_mcp: FilesystemMcp) -> None:
    policies = create_access_control_driver(database=filesystem_invocation_mcp.database)
    principal = Principal(type=PrincipalType.USER, issuer="https://issuer", id="bob")
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = UUID(await create_node(client, await root_id(client), "empty", "file"))
        await policies.add_grant(AccessGrant(
            node_id=node_id, principal=principal, permissions={Permission.DISCOVER, Permission.READ}, recursive=False,
        ))
        filesystem_invocation_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", (), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        resource = FilesystemFileResource(node_id, filesystem_invocation_mcp.callers, filesystem_invocation_mcp.services)
        result = await client.read_resource(file_resource_uri(node_id))
        assert isinstance(result[0], BlobResourceContents)
        await policies.remove_grant(node_id, principal)
        with pytest.raises(ResourceError, match=DENIED):
            await resource.read()
        with pytest.raises(MCPError, match=DENIED):
            await client.read_resource(file_resource_uri(node_id))


@pytest.mark.asyncio
async def test_scope_guard_blocks_retained_resource_before_capture_and_services(filesystem_invocation_mcp: FilesystemMcp) -> None:
    services = Mock(spec=FilesystemServiceFactory)
    resource = FilesystemFileResource(uuid4(), filesystem_invocation_mcp.callers, services)
    captures = filesystem_invocation_mcp.callers.count
    token = set_request_connector_scope("connector-only")
    try:
        with pytest.raises(ResourceError, match=DENIED):
            await resource.read()
        services.content.assert_not_called()
        assert filesystem_invocation_mcp.callers.count == captures
        async with Client(filesystem_invocation_mcp.server) as client:
            with pytest.raises(MCPError, match=DENIED):
                await client.read_resource(str(resource.uri))
    finally:
        reset_request_connector_scope(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["invalid", "{uuid}/", "{uuid}?revision=1", "{uuid}#old", "{uuid}/content", "{hex}", "{upper}"])
async def test_noncanonical_uri_fails_before_capture(filesystem_invocation_mcp: FilesystemMcp, suffix: str) -> None:
    node_id = uuid4()
    uri = "umbod://filesystem/files/" + suffix.format(uuid=node_id, hex=node_id.hex, upper=str(node_id).upper())
    template = FilesystemFileResourceTemplate(filesystem_invocation_mcp.callers, filesystem_invocation_mcp.services)
    captures = filesystem_invocation_mcp.callers.count
    with pytest.raises(ResourceError, match="filesystem_invalid_read"):
        await template.create_resource(uri, {"node_id": uri.rsplit("/", 1)[-1]})
    assert filesystem_invocation_mcp.callers.count == captures


@pytest.mark.asyncio
async def test_reads_create_fresh_services_and_capture_each_caller(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        published = await publish(client, b"hello", "text/plain")
    node_id = UUID(published["id"])
    factory = Mock(spec=FilesystemServiceFactory)
    services = [Mock(spec=FilesystemContent), Mock(spec=FilesystemContent)]
    for service in services:
        service.open_download = AsyncMock(side_effect=filesystem_invocation_mcp.files.open_download)
    factory.content.side_effect = services
    resource = FilesystemFileResource(node_id, filesystem_invocation_mcp.callers, factory)
    captures = filesystem_invocation_mcp.callers.count
    await resource.read()
    await resource.read()
    assert factory.content.call_count == 2
    assert filesystem_invocation_mcp.callers.count == captures + 2
    for service in services:
        service.open_download.assert_awaited_once_with(filesystem_invocation_mcp.callers.current.get(), node_id)


@pytest.mark.asyncio
async def test_concurrent_callers_remain_isolated(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        published = await publish(client, b"secret", "text/plain")
    resource = FilesystemFileResource(UUID(published["id"]), filesystem_invocation_mcp.callers, filesystem_invocation_mcp.services)

    async def read_as(subject: str) -> str:
        token = filesystem_invocation_mcp.callers.current.set(caller_snapshot(
            subject, "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        try:
            await asyncio.sleep(0)
            try:
                await resource.read()
                return "allowed"
            except ResourceError as error:
                return str(error)
        finally:
            filesystem_invocation_mcp.callers.current.reset(token)

    assert await asyncio.gather(read_as("alice"), read_as("bob")) == ["allowed", DENIED]


@pytest.mark.asyncio
async def test_read_keeps_captured_revision_and_bytes_during_namespace_update(
    filesystem_invocation_mcp: FilesystemMcp, monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = create_namespace_driver(database=filesystem_invocation_mcp.database)
    async with Client(filesystem_invocation_mcp.server) as client:
        published = await publish(client, b"original", "text/plain")
        node_id = UUID(published["id"])
        replacement = await publish(client, b"replacement", "text/plain")
        replacement_node = await namespace.get_node(UUID(replacement["id"]))
        original_get = filesystem_invocation_mcp.content.get

        async def update_then_stream(key: StorageKey) -> ByteStream:
            await namespace.update_node(
                node_id, content=replacement_node.content, expected_revision=published["revision"],
            )
            async for chunk in original_get(key):
                yield chunk

        monkeypatch.setattr(filesystem_invocation_mcp.content, "get", update_then_stream)
        result = await client.read_resource(file_resource_uri(node_id))
    assert result[0].text == "original"
    assert result[0].meta == {"revision": published["revision"], "size_bytes": 8}
    assert (await namespace.get_node(node_id)).revision == published["revision"] + 1


@pytest.mark.asyncio
async def test_resource_read_cap_is_independent_of_upload_limit(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        published = await publish(client, b"readable", "text/plain")
    factory = DatabaseFilesystemServiceFactory(
        filesystem_invocation_mcp.database, filesystem_invocation_mcp.content, 0, "https://issuer", "https://api.example",
    )
    result = await FilesystemFileResource(
        UUID(published["id"]), filesystem_invocation_mcp.callers, factory,
    ).read()
    assert result.contents[0].content == "readable"


@pytest.mark.asyncio
async def test_directory_resource_is_not_readable(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        node_id = UUID(await create_node(client, await root_id(client), "directory", "directory"))
        with pytest.raises(MCPError, match="filesystem_wrong_node_kind"):
            await client.read_resource(file_resource_uri(node_id))


@pytest.mark.asyncio
async def test_oversize_resource_has_no_partial_response(filesystem_invocation_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_invocation_mcp.server) as client:
        published = await publish(client, b"x" * (MAX_READ_BYTES + 1), "text/plain")
        with pytest.raises(MCPError, match="filesystem_read_too_large"):
            await client.read_resource(file_resource_uri(UUID(published["id"])))
