from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from umbod.core.callers import CallerSnapshot

from ..authorization import (
    FilesystemIdentityResolver, PermissionDenied, ResolvedIdentity, UnresolvedIdentity,
    allows_resolved,
)
from ..browsing import summary
from ..content.errors import UploadTooLarge
from ..creation.service import require_unowned_unshared_node
from ..errors import MissingNode
from ..models import NodeId, NodeKind, NodeMetadata, Ownership, Permission
from ..namespace import require_directory, validate_name
from ..ports import ByteStream, ContentDriver
from .errors import UploadConflict, UploadExpired, UploadLengthMismatch, UploadMediaTypeMismatch
from .models import CompletedUpload, PendingUpload, UploadCompletion, UploadedContent, UploadSession
from .ports import UploadClock, UploadTransaction, UploadTransactions


class SystemUploadClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class UploadService:
    def __init__(
        self, resolver: FilesystemIdentityResolver, transactions: UploadTransactions,
        content: ContentDriver, max_upload_bytes: int, clock: UploadClock,
        ttl: timedelta,
    ) -> None:
        if max_upload_bytes < 0 or ttl <= timedelta(0):
            raise ValueError("Invalid upload limits")
        self._resolver = resolver
        self._transactions = transactions
        self._content = content
        self._max_upload_bytes = max_upload_bytes
        self._clock = clock
        self._ttl = ttl

    async def _identity(self, snapshot: CallerSnapshot) -> ResolvedIdentity:
        identity = await self._resolver.resolve(snapshot)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied()
        return identity

    async def _parent(
        self, session: UploadTransaction, identity: ResolvedIdentity, parent_id: NodeId,
    ) -> None:
        for permission in (Permission.DISCOVER, Permission.WRITE):
            if not await allows_resolved(
                identity, parent_id, permission, session.namespace, session.access_control,
            ):
                raise PermissionDenied()
        require_directory(await session.namespace.get_node(parent_id))

    async def authorize_begin(self, snapshot: CallerSnapshot, parent_id: NodeId) -> None:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            await self._parent(session, identity, parent_id)

    async def begin(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str,
        metadata: NodeMetadata, size_bytes: int,
    ) -> UploadSession:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            await self._parent(session, identity, parent_id)
            validate_name(name)
            if size_bytes < 0:
                raise UploadLengthMismatch()
            if size_bytes > self._max_upload_bytes:
                raise UploadTooLarge()
            upload = UploadSession(
                id=uuid4(), owner=identity.user, parent_id=parent_id, name=name,
                metadata=metadata, size_bytes=size_bytes,
                expires_at=self._clock.now() + self._ttl, progress=PendingUpload(),
            )
            await session.uploads.save(upload)
            return upload

    async def _load(
        self, session: UploadTransaction, identity: ResolvedIdentity, upload_id: UUID,
    ) -> UploadSession:
        upload = await session.uploads.get(upload_id)
        if upload is None or upload.owner != identity.user:
            raise PermissionDenied()
        await self._parent(session, identity, upload.parent_id)
        if not isinstance(upload.progress, CompletedUpload) and self._clock.now() >= upload.expires_at:
            raise UploadExpired()
        return upload

    async def get(self, snapshot: CallerSnapshot, upload_id: UUID) -> UploadSession:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            return await self._load(session, identity, upload_id)

    async def _bounded(self, data: ByteStream, declared_size: int) -> ByteStream:
        size = 0
        async for chunk in data:
            size += len(chunk)
            if size > self._max_upload_bytes or size > declared_size:
                raise UploadTooLarge()
            yield chunk
        if size != declared_size:
            raise UploadLengthMismatch()

    async def put(
        self, snapshot: CallerSnapshot, upload_id: UUID, content_type: str, data: ByteStream,
    ) -> None:
        upload = await self.get(snapshot, upload_id)
        if isinstance(upload.progress, CompletedUpload):
            raise UploadConflict()
        expected_type = upload.metadata.content_type
        if not isinstance(expected_type, str):
            expected_type = "application/octet-stream"
        if content_type != expected_type:
            raise UploadMediaTypeMismatch()
        content = await self._content.put(self._bounded(data, upload.size_bytes))
        if content.size != upload.size_bytes:
            raise UploadLengthMismatch()
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            current = await self._load(session, identity, upload_id)
            if isinstance(current.progress, CompletedUpload):
                raise UploadConflict()
            await session.uploads.save(current.model_copy(update={"progress": UploadedContent(content=content)}))

    async def complete(self, snapshot: CallerSnapshot, upload_id: UUID) -> UploadCompletion:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            upload = await self._load(session, identity, upload_id)
            if isinstance(upload.progress, CompletedUpload):
                try:
                    await session.namespace.get_node(upload.progress.node.id)
                except MissingNode:
                    raise PermissionDenied() from None
                return UploadCompletion(node=upload.progress.node, created=False)
            if not isinstance(upload.progress, UploadedContent):
                raise UploadConflict()
            if max(upload.size_bytes, upload.progress.content.size) > self._max_upload_bytes:
                raise UploadTooLarge()
            node = await session.namespace.create_node(
                upload.parent_id, upload.name, NodeKind.FILE, upload.metadata,
            )
            await require_unowned_unshared_node(session, node.id)
            await session.access_control.set_owner(Ownership(node_id=node.id, owner=identity.user))
            node = await session.namespace.update_node(
                node.id, content=upload.progress.content, expected_revision=node.revision,
            )
            result = summary(node)
            await session.uploads.save(upload.model_copy(update={"progress": CompletedUpload(node=result)}))
            return UploadCompletion(node=result, created=True)
