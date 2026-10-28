from umbod.core.callers import CallerSnapshot

from ..authorization import (
    FilesystemIdentityResolver,
    PermissionDenied,
    ResolvedIdentity,
    UnresolvedIdentity,
    allows_resolved,
)
from ..browsing import NodeSummary, summary
from ..creation.service import require_unowned_unshared_node
from ..errors import NameCollision, WrongNodeKind
from ..models import EmptyContent, NodeId, NodeKind, NodeMetadata, Ownership, Permission
from ..namespace import require_directory, validate_name
from ..ports import ByteStream, ContentDriver
from ..transactions import FilesystemSession, FilesystemTransactions
from .errors import UploadTooLarge
from .models import ContentDownload


async def empty_stream() -> ByteStream:
    yield b""


class ContentService:
    def __init__(
        self, resolver: FilesystemIdentityResolver, transactions: FilesystemTransactions,
        content: ContentDriver, max_upload_bytes: int,
    ) -> None:
        if max_upload_bytes < 0:
            raise ValueError("Upload limit must be nonnegative")
        self._resolver = resolver
        self._transactions = transactions
        self._content = content
        self._max_upload_bytes = max_upload_bytes

    async def _identity(self, snapshot: CallerSnapshot) -> ResolvedIdentity:
        identity = await self._resolver.resolve(snapshot)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied("Unresolved filesystem identity")
        return identity

    async def _require(
        self, session: FilesystemSession, identity: ResolvedIdentity,
        node_id: NodeId, permissions: tuple[Permission, ...],
    ) -> None:
        for permission in permissions:
            if not await allows_resolved(
                identity, node_id, permission, session.namespace, session.access_control
            ):
                raise PermissionDenied(f"{permission.value} denied for node {node_id}")

    async def _require_parent(
        self, session: FilesystemSession, identity: ResolvedIdentity, parent_id: NodeId,
    ) -> None:
        await self._require(session, identity, parent_id, (Permission.DISCOVER, Permission.WRITE))
        require_directory(await session.namespace.get_node(parent_id))

    async def authorize_upload(self, snapshot: CallerSnapshot, parent_id: NodeId) -> None:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            await self._require_parent(session, identity, parent_id)

    async def _bounded(self, data: ByteStream) -> ByteStream:
        size = 0
        async for chunk in data:
            size += len(chunk)
            if size > self._max_upload_bytes:
                raise UploadTooLarge("Upload exceeds configured byte limit")
            yield chunk

    async def upload(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str,
        metadata: NodeMetadata, data: ByteStream,
    ) -> NodeSummary:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            await self._require_parent(session, identity, parent_id)
            validate_name(name)
            if any(child.name == name for child in await session.namespace.list_children(parent_id)):
                raise NameCollision(name)
        content = await self._content.put(self._bounded(data))
        async with self._transactions.transaction() as session:
            await self._require_parent(session, identity, parent_id)
            node = await session.namespace.create_node(parent_id, name, NodeKind.FILE, metadata)
            await require_unowned_unshared_node(session, node.id)
            await session.access_control.set_owner(Ownership(node_id=node.id, owner=identity.user))
            updated = await session.namespace.update_node(
                node.id, content=content, expected_revision=node.revision
            )
            result = summary(updated)
        return result

    async def open_download(
        self, snapshot: CallerSnapshot, node_id: NodeId,
    ) -> ContentDownload:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            await self._require(session, identity, node_id, (Permission.DISCOVER, Permission.READ))
            node = await session.namespace.get_node(node_id)
            if node.kind != NodeKind.FILE:
                raise WrongNodeKind(str(node_id))
            result = summary(node)
            content = node.content
        if isinstance(content, EmptyContent):
            return ContentDownload(node=result, data=empty_stream(), size=0)
        return ContentDownload(node=result, data=self._content.get(content.key), size=content.size)
