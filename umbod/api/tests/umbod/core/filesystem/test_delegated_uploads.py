import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from umbod.core.filesystem import AccessGrant, ByteStream, Permission, Principal, PrincipalType
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.stores.uploads import DatabaseUploadTransactions
from umbod.core.filesystem.uploads import UploadService, UploadTransactions
from umbod.core.filesystem.uploads.ports import UploadTransaction
from umbod.core.filesystem.uploads.errors import (
    UploadChecksumMismatch, UploadConflict, UploadLengthMismatch, UploadReceiptUnavailable,
)
from umbod.core.filesystem.uploads.models import (
    ClaimedTransfer, CompletedUpload, DelegatedTransfer, ExpectedChecksum,
    NoDelegatedTransfer, NoExpectedChecksum, UnavailableReceipt, UploadedContent, UploadSession, VerifiedReceipt,
)
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import InMemoryContentConfig, LocalContentConfig, create_content_driver

from tests.umbod.core.filesystem.test_authorized_content import alice, caller, metadata, stream
from tests.umbod.core.filesystem.test_authorized_content import content_context as content_context
from tests.umbod.core.filesystem.test_upload_sessions import UploadContext
from tests.umbod.core.filesystem.test_upload_sessions import uploads as uploads
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [(b"",), (b"\x00\xff\xfe",), (b"a", b"\x00", b"bc", b"")])
@pytest.mark.parametrize("backend", ["inmemory", "local"])
async def test_streamed_receipts_survive_completion_and_expiry(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime, tmp_path: Path,
    chunks: tuple[bytes, ...], backend: str,
) -> None:
    config = InMemoryContentConfig(type="inmemory") if backend == "inmemory" else LocalContentConfig(
        type="local", directory=tmp_path / "content",
    )
    service = UploadService(
        VerifiedIdentityResolver(), DatabaseUploadTransactions(filesystem_runtime.database),
        create_content_driver(config), 6, uploads.clock, timedelta(hours=1),
    )
    payload = b"".join(chunks)
    receipt = VerifiedReceipt(size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    delegated = await service.begin_delegated(
        caller(), ROOT_ID, "receipt", metadata(), len(payload), ExpectedChecksum(sha256=receipt.sha256),
    )
    assert delegated.expires_at == uploads.clock.now() + timedelta(minutes=15)
    assert delegated.session.expires_at == uploads.clock.now() + timedelta(hours=1)
    assert delegated.token not in delegated.session.model_dump_json()
    await service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", stream(*chunks))
    staged = await service.get(caller(), delegated.session.id)
    assert isinstance(staged.progress, UploadedContent)
    assert staged.progress.receipt == receipt
    completed = await service.complete_verified(caller(), staged.id)
    uploads.clock.current += timedelta(days=1)
    retried = await service.complete_verified(caller(), staged.id)
    assert retried.node == completed.node
    assert retried.receipt == completed.receipt == receipt
    assert not retried.created


@pytest.mark.asyncio
async def test_checksum_mismatch_prevents_publication_and_releases_claim(uploads: UploadContext) -> None:
    delegated = await uploads.service.begin_delegated(
        caller(), ROOT_ID, "checksum", metadata(), 2,
        ExpectedChecksum(sha256=hashlib.sha256(b"ok").hexdigest()),
    )
    with pytest.raises(UploadChecksumMismatch):
        await uploads.service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", stream(b"no"))
    with pytest.raises(UploadConflict):
        await uploads.service.complete(caller(), delegated.session.id)
    assert await uploads.content.namespace.list_children(ROOT_ID) == []
    await uploads.service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", stream(b"o", b"k"))
    assert (await uploads.service.complete(caller(), delegated.session.id)).receipt == VerifiedReceipt(
        size_bytes=2, sha256=hashlib.sha256(b"ok").hexdigest(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["short", "interrupted", "cancelled"])
async def test_failed_delegated_transfer_can_retry(uploads: UploadContext, failure: str) -> None:
    delegated = await uploads.service.begin_delegated(caller(), ROOT_ID, "retry", metadata(), 2, NoExpectedChecksum())

    async def broken() -> ByteStream:
        yield b"a"
        if failure == "interrupted":
            raise ConnectionError()
        if failure == "cancelled":
            raise asyncio.CancelledError()

    error = {"short": UploadLengthMismatch, "interrupted": ConnectionError, "cancelled": asyncio.CancelledError}[failure]
    with pytest.raises(error):
        await uploads.service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", broken())
    await uploads.service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", stream(b"ok"))
    assert (await uploads.service.complete(caller(), delegated.session.id)).created


@pytest.mark.asyncio
async def test_claim_admission_rejects_concurrent_and_replayed_bytes(uploads: UploadContext) -> None:
    delegated = await uploads.service.begin_delegated(caller(), ROOT_ID, "once", metadata(), 1, NoExpectedChecksum())
    entered = asyncio.Event()
    resume = asyncio.Event()
    reads: list[bool] = []

    async def slow() -> ByteStream:
        entered.set()
        await resume.wait()
        yield b"x"

    async def forbidden() -> ByteStream:
        reads.append(True)
        yield b"y"

    first = asyncio.create_task(uploads.service.put_delegated(
        delegated.session.id, delegated.token, "application/octet-stream", slow(),
    ))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        with pytest.raises(UploadConflict):
            await uploads.service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", forbidden())
    finally:
        resume.set()
        await first
    with pytest.raises(UploadConflict):
        await uploads.service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", forbidden())
    with pytest.raises(UploadConflict):
        await uploads.service.put(caller(), delegated.session.id, "application/octet-stream", forbidden())
    assert reads == []
    completed = await uploads.service.complete(caller(), delegated.session.id)
    assert completed.receipt == VerifiedReceipt(size_bytes=1, sha256=hashlib.sha256(b"x").hexdigest())
    with pytest.raises(UploadConflict):
        await uploads.service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", forbidden())
    assert reads == []


@pytest.mark.asyncio
@pytest.mark.parametrize("token_kind", ["empty", "wrong", "unicode", "tampered", "other_upload", "expired"])
async def test_capabilities_deny_before_reading_any_body(uploads: UploadContext, token_kind: str) -> None:
    delegated = await uploads.service.begin_delegated(caller(), ROOT_ID, "private", metadata(), 1, NoExpectedChecksum())
    other = await uploads.service.begin_delegated(caller(), ROOT_ID, "other", metadata(), 1, NoExpectedChecksum())
    token = {
        "empty": "", "wrong": "x" * 43, "unicode": "é" * 43,
        "tampered": ("A" if delegated.token[0] != "A" else "B") + delegated.token[1:],
        "other_upload": other.token, "expired": delegated.token,
    }[token_kind]
    if token_kind == "expired":
        uploads.clock.current += timedelta(minutes=15)
    reads: list[bool] = []

    async def forbidden() -> ByteStream:
        reads.append(True)
        yield b"x"

    for identifier in (delegated.session.id, uuid4()):
        with pytest.raises(PermissionDenied):
            await uploads.service.put_delegated(identifier, token, "application/octet-stream", forbidden())
    assert reads == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["admission", "during_io", "expiry_during_io"])
async def test_transfer_rechecks_grants_and_expiry_without_holding_io_transaction(
    uploads: UploadContext, stage: str,
) -> None:
    delegated = await uploads.service.begin_delegated(caller(), ROOT_ID, "revoked", metadata(), 1, NoExpectedChecksum())
    if stage == "admission":
        await uploads.content.policies.remove_grant(ROOT_ID, alice())
    reads: list[bool] = []

    async def data() -> ByteStream:
        reads.append(True)
        if stage == "during_io":
            await uploads.content.policies.remove_grant(ROOT_ID, alice())
        if stage == "expiry_during_io":
            uploads.clock.current += timedelta(minutes=15)
        yield b"x"

    with pytest.raises(PermissionDenied):
        await asyncio.wait_for(uploads.service.put_delegated(
            delegated.session.id, delegated.token, "application/octet-stream", data(),
        ), 5)
    assert bool(reads) == (stage != "admission")
    assert await uploads.content.namespace.list_children(ROOT_ID) == []


@pytest.mark.asyncio
async def test_completion_rechecks_fresh_caller_membership_and_owner(uploads: UploadContext) -> None:
    group = Principal(type=PrincipalType.GROUP, issuer="issuer", id="writers")
    await uploads.content.policies.add_grant(AccessGrant(
        node_id=ROOT_ID, principal=group, permissions=frozenset({Permission.DISCOVER, Permission.WRITE}), recursive=False,
    ))
    await uploads.content.policies.remove_grant(ROOT_ID, alice())
    issuance = snapshot("alice", "issuer", ("writers",))
    delegated = await uploads.service.begin_delegated(issuance, ROOT_ID, "groups", metadata(), 1, NoExpectedChecksum())
    await uploads.service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", stream(b"x"))
    for fresh in (caller(), snapshot("bob", "issuer", ("writers",))):
        with pytest.raises(PermissionDenied):
            await uploads.service.complete(fresh, delegated.session.id)
    assert await uploads.content.namespace.list_children(ROOT_ID) == []
    assert (await uploads.service.complete(issuance, delegated.session.id)).created


@pytest.mark.asyncio
async def test_legacy_json_keeps_unavailable_receipt_and_old_completion_compatible(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "legacy", metadata(), 1)
    await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))
    staged = await uploads.service.get(caller(), upload.id)
    payload = staged.model_dump(mode="json")
    payload.pop("delegated_transfer")
    payload.pop("expected_checksum")
    payload["progress"].pop("receipt")
    legacy = UploadSession.model_validate(payload)
    assert isinstance(legacy.delegated_transfer, NoDelegatedTransfer)
    assert isinstance(legacy.progress.receipt, UnavailableReceipt)
    transactions = DatabaseUploadTransactions(filesystem_runtime.database)
    async with transactions.transaction() as transaction:
        await transaction.uploads.save(legacy)
    with pytest.raises(UploadReceiptUnavailable):
        await uploads.service.complete_verified(caller(), upload.id)
    assert await uploads.content.namespace.list_children(ROOT_ID) == []
    completed = await uploads.service.complete(caller(), upload.id)
    assert isinstance(completed.receipt, UnavailableReceipt)
    stored = await uploads.service.get(caller(), upload.id)
    assert isinstance(stored.progress, CompletedUpload)
    old_completed = stored.model_dump(mode="json")
    old_completed["progress"].pop("receipt")
    assert isinstance(UploadSession.model_validate(old_completed).progress.receipt, UnavailableReceipt)


class CancelAfterCommitTransactions:
    def __init__(self, delegate: UploadTransactions) -> None:
        self._delegate = delegate
        self._cancel_next_exit = True

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[UploadTransaction]:
        async with self._delegate.transaction() as transaction:
            yield transaction
        if self._cancel_next_exit:
            self._cancel_next_exit = False
            raise asyncio.CancelledError()


@pytest.mark.asyncio
async def test_cancellation_after_claim_commit_releases_claim(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    delegated = await uploads.service.begin_delegated(caller(), ROOT_ID, "cancelled-commit", metadata(), 1, NoExpectedChecksum())
    service = UploadService(
        VerifiedIdentityResolver(), CancelAfterCommitTransactions(DatabaseUploadTransactions(filesystem_runtime.database)),
        uploads.content.content, 6, uploads.clock, timedelta(hours=1),
    )
    with pytest.raises(asyncio.CancelledError):
        await service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", stream(b"x"))
    await service.put_delegated(delegated.session.id, delegated.token, "application/octet-stream", stream(b"x"))
    assert (await service.complete(caller(), delegated.session.id)).created


@pytest.mark.asyncio
async def test_crashed_claim_is_not_stolen(uploads: UploadContext, filesystem_runtime: PersistenceRuntime) -> None:
    delegated = await uploads.service.begin_delegated(caller(), ROOT_ID, "crashed", metadata(), 1, NoExpectedChecksum())
    grant = delegated.session.delegated_transfer
    assert isinstance(grant, DelegatedTransfer)
    crashed = delegated.session.model_copy(update={
        "delegated_transfer": grant.model_copy(update={"state": ClaimedTransfer(claim_id=uuid4())}),
    })
    async with DatabaseUploadTransactions(filesystem_runtime.database).transaction() as transaction:
        await transaction.uploads.save(crashed)
    with pytest.raises(UploadConflict):
        await uploads.service.put_delegated(crashed.id, delegated.token, "application/octet-stream", stream(b"x"))
    assert await uploads.content.namespace.list_children(ROOT_ID) == []
