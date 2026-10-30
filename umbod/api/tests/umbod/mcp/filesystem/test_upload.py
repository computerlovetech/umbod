import base64
from typing import Any
from uuid import UUID

import pytest
from fastmcp import Client
from fastmcp.client.client import CallToolResult

from umbod.core.callers import (
    AuthenticationProvenance, CallerContext, CallerSnapshot, GroupMembership, UnavailableSubject,
)

from .conftest import FilesystemMcp, caller_snapshot
from .test_tools import METADATA, root_id

CAP = 10_485_760


async def upload(client: Client, parent: str, content: dict[str, Any]) -> CallToolResult:
    return await client.call_tool("filesystem_upload", {
        "parent_id": parent, "name": "uploaded", "metadata": METADATA, "content": content,
    }, raise_on_error=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("content,expected", [
    ({"encoding": "utf-8", "text": "Hej 世界 🌍"}, "Hej 世界 🌍".encode()),
    ({"encoding": "base64", "data": "AP/+AA=="}, b"\x00\xff\xfe\x00"),
    ({"encoding": "utf-8", "text": ""}, b""),
    ({"encoding": "base64", "data": ""}, b""),
    ({"encoding": "utf-8", "text": "a" * CAP}, b"a" * CAP),
    ({"encoding": "base64", "data": base64.b64encode(b"x" * CAP).decode()}, b"x" * CAP),
], ids=["unicode", "binary", "empty-text", "empty-base64", "text-cap", "binary-cap"])
async def test_upload_publishes_readable_private_content(
    filesystem_mcp: FilesystemMcp, content: dict[str, Any], expected: bytes,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        parent = await root_id(client)
        before = filesystem_mcp.callers.count
        result = await upload(client, parent, content)
    assert not result.is_error
    assert filesystem_mcp.callers.count == before + 1
    assert result.content[0].text == "File uploaded successfully."
    assert set(result.structured_content) == {
        "id", "parent_id", "name", "kind", "metadata", "created_at", "updated_at", "revision",
    }
    download = await filesystem_mcp.files.open_download(
        filesystem_mcp.callers.current.get(), UUID(result.structured_content["id"]),
    )
    assert b"".join([chunk async for chunk in download.data]) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [
    {"encoding": "utf-8", "text": "x" * (CAP + 1)},
    {"encoding": "utf-8", "text": "é" * (CAP // 2 + 1)},
    {"encoding": "base64", "data": base64.b64encode(b"x" * (CAP + 1)).decode()},
    {"encoding": "base64", "data": base64.b64encode(b"x" * (CAP + 2)).decode()},
    {"encoding": "base64", "data": "A" * 13_981_020},
])
async def test_oversize_is_rejected_before_storage(
    filesystem_mcp: FilesystemMcp, content: dict[str, Any],
) -> None:
    async with Client(filesystem_mcp.server) as client:
        result = await upload(client, await root_id(client), content)
        listed = await client.call_tool("list_filesystem_children", {
            "parent_id": await root_id(client),
        })
    assert result.is_error
    assert result.content[0].text == "filesystem_upload_too_large: Filesystem upload too large"
    assert filesystem_mcp.content.put_count == 0
    assert listed.structured_content == {"nodes": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [
    {"encoding": "base64", "data": "Zg"},
    {"encoding": "base64", "data": "Zh=="},
    {"encoding": "base64", "data": "Zg==="},
    {"encoding": "base64", "data": "Zg==\n"},
    {"encoding": "base64", "data": "_w=="},
    {"encoding": "base64", "data": "秘密"},
    {"encoding": "utf-8", "text": "\ud800"},
    {"encoding": "utf-8", "text": "SECRET", "owner": "alice"},
    {"encoding": "unknown", "text": "SECRET"},
])
async def test_invalid_content_is_sanitized_without_storage(
    filesystem_mcp: FilesystemMcp, content: dict[str, Any],
) -> None:
    async with Client(filesystem_mcp.server) as client:
        result = await upload(client, await root_id(client), content)
    assert result.is_error
    assert "SECRET" not in result.content[0].text
    assert filesystem_mcp.content.put_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["owner", "caller", "storage_key", "identity", "operation"])
async def test_upload_rejects_extra_authority_fields(
    filesystem_mcp: FilesystemMcp, field: str,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        result = await client.call_tool("filesystem_upload", {
            "parent_id": await root_id(client), "name": "uploaded", "metadata": METADATA,
            "content": {"encoding": "utf-8", "text": "SECRET"}, field: "SECRET",
        }, raise_on_error=False)
    assert result.is_error
    assert "SECRET" not in result.content[0].text
    assert filesystem_mcp.content.put_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("issuer,provenance", [
    ("https://other", AuthenticationProvenance.UPSTREAM_VERIFIED),
    ("https://issuer", AuthenticationProvenance.LOCAL_TEST),
])
async def test_upload_rejects_untrusted_callers(
    filesystem_mcp: FilesystemMcp, issuer: str, provenance: AuthenticationProvenance,
) -> None:
    async with Client(filesystem_mcp.server) as client:
        parent = await root_id(client)
        filesystem_mcp.callers.current.set(caller_snapshot("alice", issuer, ("writers",), provenance))
        result = await upload(client, parent, {"encoding": "utf-8", "text": "secret"})
    assert result.is_error
    assert "filesystem_permission_denied" in result.content[0].text
    assert filesystem_mcp.content.put_count == 0


@pytest.mark.asyncio
async def test_upload_without_authentication_is_denied(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        parent = await root_id(client)
        filesystem_mcp.callers.current.set(CallerSnapshot(
            caller=CallerContext(
                authentication=AuthenticationProvenance.UNAVAILABLE,
                subject=UnavailableSubject(kind="unavailable"),
            ), groups=GroupMembership(group_ids=()),
        ))
        result = await upload(client, parent, {"encoding": "utf-8", "text": "secret"})
    assert result.is_error
    assert "filesystem_permission_denied" in result.content[0].text
    assert filesystem_mcp.content.put_count == 0


@pytest.mark.asyncio
async def test_upload_collision_has_safe_error(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        parent = await root_id(client)
        assert not (await upload(client, parent, {"encoding": "utf-8", "text": "one"})).is_error
        result = await upload(client, parent, {"encoding": "utf-8", "text": "two"})
    assert result.is_error
    assert result.content[0].text == "filesystem_name_collision: Filesystem name already exists"


@pytest.mark.asyncio
async def test_upload_to_other_users_private_directory_is_denied(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        directory = await client.call_tool("create_filesystem_directory", {
            "parent_id": await root_id(client), "name": "private", "metadata": METADATA,
        })
        filesystem_mcp.callers.current.set(caller_snapshot(
            "bob", "https://issuer", ("writers",), AuthenticationProvenance.UPSTREAM_VERIFIED,
        ))
        result = await upload(client, str(directory.data.id), {"encoding": "utf-8", "text": "secret"})
    assert result.is_error
    assert "filesystem_permission_denied" in result.content[0].text
    assert filesystem_mcp.content.put_count == 0


@pytest.mark.asyncio
async def test_upload_schema_advertises_bounds_and_mutation(filesystem_mcp: FilesystemMcp) -> None:
    async with Client(filesystem_mcp.server) as client:
        descriptor = next(tool for tool in await client.list_tools() if tool.name == "filesystem_upload")
    assert set(descriptor.input_schema["required"]) == {"parent_id", "name", "metadata", "content"}
    variants = descriptor.input_schema["properties"]["content"]["oneOf"]
    assert variants[0]["properties"]["text"]["maxLength"] == CAP
    assert variants[1]["properties"]["data"]["maxLength"] == 13_981_016
    assert "10485760" in descriptor.description
    assert descriptor.annotations.read_only_hint is False
    assert descriptor.annotations.destructive_hint is False
    assert descriptor.annotations.idempotent_hint is False
    assert descriptor.annotations.open_world_hint is False
