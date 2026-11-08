import hashlib
import hmac
import secrets

import anyio

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
from .errors import (
    UploadChecksumMismatch, UploadConflict, UploadExpired, UploadLengthMismatch,
    UploadMediaTypeMismatch, UploadReceiptUnavailable,
)
from .models import (
    AvailableTransfer, ChecksumExpectation, ClaimedTransfer, CompletedUpload, ConsumedTransfer,
    DelegatedTransfer, DelegatedUpload, ExpectedChecksum, NoDelegatedTransfer,
    ExternalTransfer, ExternalTransferRequest, ExternalTransferInstructions, UnavailableExternalTransfer,
    NoExpectedChecksum, PendingUpload, TransferGrant, UploadCompletion, UploadedContent,
    UploadSession, VerifiedReceipt,
)
from .ports import ExternalUploadTransfer, UploadClock, UploadTransaction, UploadTransactions


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

    async def begin(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str,
        metadata: NodeMetadata, size_bytes: int,
    ) -> UploadSession:
        return await self._begin(
            await self._identity(snapshot), parent_id, name, metadata, size_bytes,
            NoExpectedChecksum(), NoDelegatedTransfer(),
        )

    @property
    def supports_external_transfer(self) -> bool:
        return isinstance(self._content, ExternalUploadTransfer)

    async def begin_transfer(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str,
        metadata: NodeMetadata, size_bytes: int, expected_checksum: ChecksumExpectation,
    ) -> UploadSession:
        grant: TransferGrant = NoDelegatedTransfer()
        if isinstance(self._content, ExternalUploadTransfer):
            if size_bytes > self._content.max_transfer_bytes:
                raise UploadTooLarge()
            grant = ExternalTransfer(
                storage_key=uuid4().hex,
                expires_at=self._clock.now() + min(self._ttl, timedelta(minutes=15)),
            )
        return await self._begin(
            await self._identity(snapshot), parent_id, name, metadata, size_bytes,
            expected_checksum, grant,
        )

    def _transfer_request(self, upload: UploadSession) -> ExternalTransferRequest:
        if not isinstance(upload.delegated_transfer, ExternalTransfer):
            raise UploadConflict()
        content_type = upload.metadata.content_type
        return ExternalTransferRequest(
            transfer=upload.delegated_transfer, size_bytes=upload.size_bytes,
            content_type=content_type if isinstance(content_type, str) else "application/octet-stream",
        )

    async def transfer_instructions(self, upload: UploadSession) -> ExternalTransferInstructions | UnavailableExternalTransfer:
        if not isinstance(self._content, ExternalUploadTransfer):
            raise UploadConflict()
        request = self._transfer_request(upload)
        if isinstance(upload.progress, CompletedUpload):
            return UnavailableExternalTransfer(reason="completed")
        if self._clock.now() >= request.transfer.expires_at:
            return UnavailableExternalTransfer(reason="expired")
        return await self._content.prepare_transfer(request)

    async def begin_delegated(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str,
        metadata: NodeMetadata, size_bytes: int, expected_checksum: ChecksumExpectation,
    ) -> DelegatedUpload:
        identity = await self._identity(snapshot)
        token = secrets.token_urlsafe(32)
        grant = DelegatedTransfer(
            token_digest=hashlib.sha256(token.encode("ascii")).hexdigest(), identity=identity,
            expires_at=self._clock.now() + min(self._ttl, timedelta(minutes=15)),
            state=AvailableTransfer(),
        )
        upload = await self._begin(identity, parent_id, name, metadata, size_bytes, expected_checksum, grant)
        return DelegatedUpload(session=upload, expires_at=min(grant.expires_at, upload.expires_at), token=token)

    async def _begin(
        self, identity: ResolvedIdentity, parent_id: NodeId, name: str,
        metadata: NodeMetadata, size_bytes: int, expected_checksum: ChecksumExpectation,
        grant: TransferGrant,
    ) -> UploadSession:
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
                expected_checksum=expected_checksum, delegated_transfer=grant,
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
        if not isinstance(upload.delegated_transfer, NoDelegatedTransfer):
            raise UploadConflict()
        if isinstance(upload.progress, CompletedUpload):
            raise UploadConflict()
        expected_type = upload.metadata.content_type
        if not isinstance(expected_type, str):
            expected_type = "application/octet-stream"
        if content_type != expected_type:
            raise UploadMediaTypeMismatch()
        staged = await self._stage(upload, data)
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            current = await self._load(session, identity, upload_id)
            if isinstance(current.progress, CompletedUpload):
                raise UploadConflict()
            await session.uploads.save(current.model_copy(update={"progress": staged}))

    def _verify_checksum(self, upload: UploadSession, staged: UploadedContent) -> None:
        if isinstance(staged.receipt, VerifiedReceipt) and (
            staged.receipt.size_bytes != upload.size_bytes or staged.content.size != upload.size_bytes
        ):
            raise UploadLengthMismatch()
        expected = upload.expected_checksum
        if isinstance(expected, ExpectedChecksum):
            if not isinstance(staged.receipt, VerifiedReceipt) or staged.receipt.sha256 != expected.sha256:
                raise UploadChecksumMismatch()

    async def _stage(self, upload: UploadSession, data: ByteStream) -> UploadedContent:
        digest = hashlib.sha256()

        async def hashed() -> ByteStream:
            async for chunk in self._bounded(data, upload.size_bytes):
                digest.update(chunk)
                yield chunk

        content = await self._content.put(hashed())
        if content.size != upload.size_bytes:
            raise UploadLengthMismatch()
        staged = UploadedContent(
            content=content,
            receipt=VerifiedReceipt(size_bytes=content.size, sha256=digest.hexdigest()),
        )
        self._verify_checksum(upload, staged)
        return staged

    async def _delegated(
        self, transaction: UploadTransaction, upload_id: UUID, token: str,
    ) -> UploadSession:
        upload = await transaction.uploads.get(upload_id)
        if upload is None or not isinstance(upload.delegated_transfer, DelegatedTransfer):
            raise PermissionDenied()
        grant = upload.delegated_transfer
        if (
            not token or len(token) != 43 or not token.isascii()
            or not hmac.compare_digest(hashlib.sha256(token.encode("ascii")).hexdigest(), grant.token_digest)
            or self._clock.now() >= min(grant.expires_at, upload.expires_at)
        ):
            raise PermissionDenied()
        await self._parent(transaction, grant.identity, upload.parent_id)
        return upload

    async def _release_claim(self, upload_id: UUID, claim_id: UUID) -> None:
        with anyio.CancelScope(shield=True):
            async with self._transactions.transaction() as transaction:
                upload = await transaction.uploads.get(upload_id)
                if upload is None or not isinstance(upload.delegated_transfer, DelegatedTransfer):
                    return
                grant = upload.delegated_transfer
                state = grant.state
                if isinstance(state, ClaimedTransfer) and state.claim_id == claim_id:
                    await transaction.uploads.save(upload.model_copy(update={
                        "delegated_transfer": grant.model_copy(update={"state": AvailableTransfer()}),
                    }))

    async def put_delegated(
        self, upload_id: UUID, token: str, content_type: str, data: ByteStream,
    ) -> None:
        claim_id = uuid4()
        try:
            async with self._transactions.transaction() as transaction:
                upload = await self._delegated(transaction, upload_id, token)
                grant = upload.delegated_transfer
                if (
                    not isinstance(grant, DelegatedTransfer)
                    or not isinstance(grant.state, AvailableTransfer)
                    or not isinstance(upload.progress, PendingUpload)
                ):
                    raise UploadConflict()
                expected_type = upload.metadata.content_type
                if content_type != (expected_type if isinstance(expected_type, str) else "application/octet-stream"):
                    raise UploadMediaTypeMismatch()
                await transaction.uploads.save(upload.model_copy(update={
                    "delegated_transfer": grant.model_copy(update={"state": ClaimedTransfer(claim_id=claim_id)}),
                }))
            staged = await self._stage(upload, data)
            async with self._transactions.transaction() as transaction:
                current = await self._delegated(transaction, upload_id, token)
                current_grant = current.delegated_transfer
                if not isinstance(current_grant, DelegatedTransfer):
                    raise UploadConflict()
                state = current_grant.state
                if (
                    not isinstance(state, ClaimedTransfer)
                    or state.claim_id != claim_id
                    or not isinstance(current.progress, PendingUpload)
                ):
                    raise UploadConflict()
                await transaction.uploads.save(current.model_copy(update={
                    "progress": staged,
                    "delegated_transfer": current_grant.model_copy(update={"state": ConsumedTransfer()}),
                }))
        except BaseException:
            await self._release_claim(upload_id, claim_id)
            raise

    async def complete(self, snapshot: CallerSnapshot, upload_id: UUID) -> UploadCompletion:
        return await self._complete(snapshot, upload_id, False)

    async def complete_verified(self, snapshot: CallerSnapshot, upload_id: UUID) -> UploadCompletion:
        return await self._complete(snapshot, upload_id, True)

    async def _complete(
        self, snapshot: CallerSnapshot, upload_id: UUID, require_verified_receipt: bool,
    ) -> UploadCompletion:
        initial = await self.get(snapshot, upload_id)
        verified: UploadedContent | PendingUpload = PendingUpload()
        if isinstance(initial.delegated_transfer, ExternalTransfer) and isinstance(initial.progress, PendingUpload):
            if initial.size_bytes > self._max_upload_bytes:
                raise UploadTooLarge()
            if not isinstance(self._content, ExternalUploadTransfer):
                raise UploadConflict()
            verified = await self._content.verify_transfer(self._transfer_request(initial))
            self._verify_checksum(initial, verified)
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            upload = await self._load(session, identity, upload_id)
            if isinstance(upload.progress, PendingUpload) and isinstance(verified, UploadedContent):
                upload = upload.model_copy(update={"progress": verified})
            if (
                require_verified_receipt and isinstance(upload.progress, (UploadedContent, CompletedUpload))
                and not isinstance(upload.progress.receipt, VerifiedReceipt)
            ):
                raise UploadReceiptUnavailable()
            if isinstance(upload.progress, CompletedUpload):
                try:
                    await session.namespace.get_node(upload.progress.node.id)
                except MissingNode:
                    raise PermissionDenied() from None
                return UploadCompletion(node=upload.progress.node, created=False, receipt=upload.progress.receipt)
            if not isinstance(upload.progress, UploadedContent):
                raise UploadConflict()
            self._verify_checksum(upload, upload.progress)
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
            await session.uploads.save(upload.model_copy(update={
                "progress": CompletedUpload(node=result, receipt=upload.progress.receipt),
            }))
            return UploadCompletion(node=result, created=True, receipt=upload.progress.receipt)
