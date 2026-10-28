import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import create_autospec

import pytest
import pytest_asyncio

from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import (
    AccessControlDriver,
    AccessGrant,
    ByteStream,
    ContentDriver,
    ContentRef,
    CreationService,
    FilesystemSession,
    FilesystemTransactions,
    InvalidName,
    NameCollision,
    NamespaceDriver,
    NodeMetadata,
    Permission,
    Principal,
    PrincipalType,
    RootBootstrapGrant,
    RootBootstrapSpec,
    StorageFailure,
    UnspecifiedContentType,
    WrongNodeKind,
)
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.content import ContentService, FilesystemContent, UploadTooLarge
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    InMemoryContentConfig,
    create_access_control_driver,
    create_content_driver,
    create_filesystem_transactions,
    create_namespace_driver,
    create_root_provisioning,
)
from tests.umbod.core.filesystem.test_verified_identity import snapshot


def metadata() -> NodeMetadata:
    return NodeMetadata(content_type=UnspecifiedContentType(), attributes={})


def alice() -> Principal:
    return Principal(type=PrincipalType.USER, issuer="issuer", id="alice")


def caller() -> CallerSnapshot:
    return snapshot("alice", "issuer", ())


async def stream(*chunks: bytes) -> ByteStream:
    for chunk in chunks:
        yield chunk


@dataclass(frozen=True)
class ContentContext:
    service: FilesystemContent
    namespace: NamespaceDriver
    policies: AccessControlDriver
    transactions: FilesystemTransactions
    content: ContentDriver
    creation: CreationService


@pytest_asyncio.fixture
async def content_context(filesystem_runtime: PersistenceRuntime) -> ContentContext:
    database = filesystem_runtime.database
    transactions = create_filesystem_transactions(database=database)
    content = create_content_driver(InMemoryContentConfig(type="inmemory"))
    resolver = VerifiedIdentityResolver()
    await create_root_provisioning(database=database).provision(RootBootstrapSpec(grants=(
        RootBootstrapGrant(
            principal=alice(),
            permissions=frozenset({Permission.DISCOVER, Permission.WRITE}),
        ),
    )))
    return ContentContext(
        service=ContentService(resolver, transactions, content, 6),
        namespace=create_namespace_driver(database=database),
        policies=create_access_control_driver(database=database),
        transactions=transactions,
        content=content,
        creation=CreationService(resolver, transactions),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [(b"abc", b"def"), (b"",)])
async def test_upload_download_roundtrip_and_private_ownership(
    content_context: ContentContext, chunks: tuple[bytes, ...],
) -> None:
    context = content_context
    node = await context.service.upload(caller(), ROOT_ID, "uploaded", metadata(), stream(*chunks))
    download = await context.service.open_download(caller(), node.id)
    assert b"".join([chunk async for chunk in download.data]) == b"".join(chunks)
    assert download.size == len(b"".join(chunks))
    assert download.node == node
    assert not hasattr(download.node, "content")
    assert node.revision == 2
    assert (await context.policies.get_owner(node.id)).owner == alice()
    assert await context.policies.list_grants(node.id) == []


@pytest.mark.asyncio
async def test_empty_created_file_download_returns_empty_stream(content_context: ContentContext) -> None:
    node = await content_context.creation.create_file(caller(), ROOT_ID, "empty", metadata())
    download = await content_context.service.open_download(caller(), node.id)
    assert b"".join([chunk async for chunk in download.data]) == b""
    assert download.size == 0


@pytest.mark.asyncio
async def test_oversize_chunk_never_reaches_content_driver(content_context: ContentContext) -> None:
    context = content_context
    received: list[bytes] = []
    content = create_autospec(ContentDriver, instance=True)

    async def put(data: ByteStream) -> ContentRef:
        async for chunk in data:
            received.append(chunk)
        raise AssertionError("Oversized stream must fail before completion")

    content.put.side_effect = put
    service = ContentService(VerifiedIdentityResolver(), context.transactions, content, 6)
    with pytest.raises(UploadTooLarge):
        await service.upload(caller(), ROOT_ID, "large", metadata(), stream(b"abc", b"defg"))
    assert received == [b"abc"]
    assert await context.namespace.list_children(ROOT_ID) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["existing", "a/b"])
async def test_invalid_name_and_collision_reject_before_consuming(
    content_context: ContentContext, name: str,
) -> None:
    context = content_context
    existing = await context.creation.create_file(caller(), ROOT_ID, "existing", metadata())
    consumed: list[bool] = []

    async def data() -> ByteStream:
        consumed.append(True)
        yield b"x"

    with pytest.raises(NameCollision if name == "existing" else InvalidName):
        await context.service.upload(caller(), ROOT_ID, name, metadata(), data())
    assert consumed == []
    assert [node.id for node in await context.namespace.list_children(ROOT_ID)] == [existing.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [set(), {Permission.DISCOVER}, {Permission.WRITE}])
async def test_permission_rejection_precedes_stream_consumption(
    content_context: ContentContext, permissions: set[Permission],
) -> None:
    context = content_context
    await context.policies.add_grant(AccessGrant(
        node_id=ROOT_ID, principal=alice(), permissions=permissions, recursive=False,
    ))
    consumed: list[bool] = []

    async def data() -> ByteStream:
        consumed.append(True)
        yield b"x"

    with pytest.raises(PermissionDenied):
        await context.service.authorize_upload(caller(), ROOT_ID)
    with pytest.raises(PermissionDenied):
        await context.service.upload(caller(), ROOT_ID, "denied", metadata(), data())
    assert consumed == []
    assert await context.namespace.list_children(ROOT_ID) == []


@pytest.mark.asyncio
async def test_unresolved_identity_rejects_before_content_put(content_context: ContentContext) -> None:
    context = content_context
    content = create_autospec(ContentDriver, instance=True)
    service = ContentService(VerifiedIdentityResolver(), context.transactions, content, 6)
    unresolved = snapshot("", "issuer", ())
    with pytest.raises(PermissionDenied):
        await service.upload(unresolved, ROOT_ID, "denied", metadata(), stream(b"x"))
    content.put.assert_not_called()


@pytest.mark.asyncio
async def test_revocation_during_upload_has_no_database_lock_and_no_visible_node(
    content_context: ContentContext,
) -> None:
    context = content_context

    async def data() -> ByteStream:
        assert await context.namespace.list_children(ROOT_ID) == []
        await context.policies.remove_grant(ROOT_ID, alice())
        yield b"x"

    with pytest.raises(PermissionDenied):
        await asyncio.wait_for(
            context.service.upload(caller(), ROOT_ID, "revoked", metadata(), data()),
            timeout=5,
        )
    assert await context.namespace.list_children(ROOT_ID) == []


@pytest.mark.asyncio
async def test_concurrent_collision_during_consumption_publishes_no_placeholder(
    content_context: ContentContext,
) -> None:
    context = content_context

    async def data() -> ByteStream:
        await context.creation.create_file(caller(), ROOT_ID, "raced", metadata())
        yield b"x"

    with pytest.raises(NameCollision):
        await asyncio.wait_for(
            context.service.upload(caller(), ROOT_ID, "raced", metadata(), data()),
            timeout=5,
        )
    children = await context.namespace.list_children(ROOT_ID)
    assert len(children) == 1
    assert children[0].revision == 1


@pytest.mark.asyncio
async def test_content_failure_leaves_no_visible_node(content_context: ContentContext) -> None:
    context = content_context
    content = create_autospec(ContentDriver, instance=True)
    content.put.side_effect = StorageFailure("content failed")
    service = ContentService(VerifiedIdentityResolver(), context.transactions, content, 6)
    with pytest.raises(StorageFailure, match="content failed"):
        await service.upload(caller(), ROOT_ID, "failed", metadata(), stream(b"x"))
    assert await context.namespace.list_children(ROOT_ID) == []


class FailingPublicationTransactions:
    def __init__(self, transactions: FilesystemTransactions, stage: str) -> None:
        self._transactions = transactions
        self._stage = stage

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FilesystemSession]:
        async with self._transactions.transaction() as session:
            namespace = create_autospec(NamespaceDriver, instance=True)
            for method in ("get_node", "list_children", "create_node", "update_node"):
                getattr(namespace, method).side_effect = getattr(session.namespace, method)
            policies = create_autospec(AccessControlDriver, instance=True)
            for method in ("get_owner", "list_grants", "set_owner"):
                getattr(policies, method).side_effect = getattr(session.access_control, method)
            target = policies.set_owner if self._stage == "owner" else namespace.update_node
            target.side_effect = StorageFailure("publication failed")
            yield FilesystemSession(namespace=namespace, access_control=policies)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["owner", "content_reference"])
async def test_publication_failure_rolls_back_created_node(
    content_context: ContentContext, stage: str,
) -> None:
    context = content_context
    service = ContentService(
        VerifiedIdentityResolver(),
        FailingPublicationTransactions(context.transactions, stage),
        context.content,
        6,
    )
    with pytest.raises(StorageFailure, match="publication failed"):
        await service.upload(caller(), ROOT_ID, "failed", metadata(), stream(b"x"))
    assert await context.namespace.list_children(ROOT_ID) == []
    node = await context.service.upload(caller(), ROOT_ID, "failed", metadata(), stream(b"x"))
    assert (await context.policies.get_owner(node.id)).owner == alice()


@pytest.mark.asyncio
async def test_directories_cannot_be_downloaded_and_file_cannot_be_upload_parent(
    content_context: ContentContext,
) -> None:
    context = content_context
    directory = await context.creation.create_directory(caller(), ROOT_ID, "directory", metadata())
    file = await context.creation.create_file(caller(), ROOT_ID, "file", metadata())
    with pytest.raises(WrongNodeKind):
        await context.service.open_download(caller(), directory.id)
    with pytest.raises(WrongNodeKind):
        await context.service.authorize_upload(caller(), file.id)
    with pytest.raises(WrongNodeKind):
        await context.service.upload(caller(), file.id, "child", metadata(), stream(b"x"))


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [{Permission.DISCOVER}, {Permission.READ}, set()])
async def test_download_requires_discover_and_read(
    content_context: ContentContext, permissions: set[Permission],
) -> None:
    context = content_context
    node = await context.creation.create_file(caller(), ROOT_ID, "private", metadata())
    bob = Principal(type=PrincipalType.USER, issuer="issuer", id="bob")
    await context.policies.add_grant(AccessGrant(
        node_id=node.id, principal=bob, permissions=permissions, recursive=False,
    ))
    with pytest.raises(PermissionDenied):
        await context.service.open_download(snapshot("bob", "issuer", ()), node.id)
