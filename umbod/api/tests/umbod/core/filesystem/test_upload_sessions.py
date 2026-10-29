import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from umbod.core.filesystem import ByteStream, ContentDriver, ContentRef, NameCollision, Permission, RootBootstrapGrant, RootBootstrapSpec, StorageFailure, StorageKey
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.content import ContentService, UploadTooLarge
from umbod.core.filesystem.deletion import DeletionService
from umbod.core.filesystem.errors import MissingNode
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.stores.uploads import DatabaseUploadTransactions
from umbod.core.filesystem.uploads import UploadService, UploadSession, UploadStore, UploadTransactions
from umbod.core.filesystem.uploads.ports import UploadTransaction
from umbod.core.filesystem.uploads.errors import UploadConflict, UploadExpired, UploadLengthMismatch
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    LocalContentConfig, create_content_driver, create_filesystem_transactions, create_namespace_driver,
    create_root_provisioning,
)
from tests.persistence_runtime import prepared_sqlite_runtime
from tests.umbod.core.filesystem.test_authorized_content import ContentContext, alice, caller, metadata, stream
from tests.umbod.core.filesystem.test_authorized_content import content_context as content_context
from tests.umbod.core.filesystem.test_verified_identity import snapshot


@pytest.mark.asyncio
async def test_completed_upload_cannot_republish_a_deleted_file(uploads: "UploadContext") -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "deleted", metadata(), 1)
    await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))
    completed = await uploads.service.complete(caller(), upload.id)
    historical = await uploads.service.get(caller(), upload.id)
    await DeletionService(VerifiedIdentityResolver(), uploads.content.transactions).delete_file(
        caller(), completed.node.id, expected_revision=completed.node.revision,
    )
    for _ in range(2):
        with pytest.raises(PermissionDenied):
            await uploads.service.complete(caller(), upload.id)
    assert await uploads.service.get(caller(), upload.id) == historical
    assert await uploads.content.namespace.list_children(ROOT_ID) == []
    with pytest.raises(MissingNode):
        await uploads.content.namespace.get_node(completed.node.id)
    replacement = await uploads.content.creation.create_file(caller(), ROOT_ID, "deleted", metadata())
    assert replacement.id != completed.node.id
    with pytest.raises(PermissionDenied):
        await uploads.service.complete(caller(), upload.id)


class Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


@dataclass
class UploadContext:
    service: UploadService
    clock: Clock
    content: ContentContext


@pytest_asyncio.fixture
async def uploads(content_context: ContentContext, filesystem_runtime: PersistenceRuntime) -> UploadContext:
    clock = Clock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    return UploadContext(
        UploadService(VerifiedIdentityResolver(), DatabaseUploadTransactions(filesystem_runtime.database),
                      content_context.content, 6, clock, timedelta(hours=1)),
        clock, content_context,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [b"", b"abc", b"abcdef"])
async def test_begin_and_transfer_are_invisible_until_atomic_completion(uploads: UploadContext, payload: bytes) -> None:
    service = uploads.service
    upload = await service.begin(caller(), ROOT_ID, "file", metadata(), len(payload))
    assert upload.progress.status == "pending"
    assert upload.expires_at == uploads.clock.now() + timedelta(hours=1)
    assert await uploads.content.namespace.list_children(ROOT_ID) == []
    await service.put(caller(), upload.id, "application/octet-stream", stream(payload))
    assert (await service.get(caller(), upload.id)).progress.status == "uploaded"
    assert await uploads.content.namespace.list_children(ROOT_ID) == []
    result = await service.complete(caller(), upload.id)
    assert result.created
    assert (await uploads.content.policies.get_owner(result.node.id)).owner == alice()
    assert await uploads.content.policies.list_grants(result.node.id) == []
    download = await uploads.content.service.open_download(caller(), result.node.id)
    assert b"".join([chunk async for chunk in download.data]) == payload


@pytest.mark.asyncio
async def test_begin_does_not_reserve_name_and_collision_preserves_completed_bytes(uploads: UploadContext) -> None:
    first = await uploads.service.begin(caller(), ROOT_ID, "same", metadata(), 1)
    second = await uploads.service.begin(caller(), ROOT_ID, "same", metadata(), 1)
    for upload in (first, second):
        await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))
    result = await uploads.service.complete(caller(), first.id)
    with pytest.raises(NameCollision):
        await uploads.service.complete(caller(), second.id)
    assert [node.id for node in await uploads.content.namespace.list_children(ROOT_ID)] == [result.node.id]
    assert (await uploads.service.get(caller(), second.id)).progress.status == "uploaded"


@pytest.mark.asyncio
@pytest.mark.parametrize("user,issuer", [("bob", "issuer"), ("alice", "foreign")])
async def test_unknown_and_foreign_sessions_fail_closed_for_all_operations(
    uploads: UploadContext, user: str, issuer: str,
) -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "private", metadata(), 1)
    foreign = snapshot(user, issuer, ())
    for identifier in (upload.id, uuid4()):
        with pytest.raises(PermissionDenied):
            await uploads.service.get(foreign, identifier)
        with pytest.raises(PermissionDenied):
            await uploads.service.complete(foreign, identifier)
        with pytest.raises(PermissionDenied):
            await uploads.service.put(foreign, identifier, "application/octet-stream", stream(b"x"))


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["before_transfer", "during_transfer", "before_completion"])
async def test_revocation_is_rechecked_without_holding_transaction_during_io(uploads: UploadContext, stage: str) -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "revoked", metadata(), 1)

    async def revoke() -> None:
        await uploads.content.policies.remove_grant(ROOT_ID, alice())

    async def data() -> ByteStream:
        if stage == "during_transfer":
            await revoke()
        yield b"x"

    if stage == "before_transfer":
        await revoke()
    if stage == "before_completion":
        await uploads.service.put(caller(), upload.id, "application/octet-stream", data())
        await revoke()
    else:
        with pytest.raises(PermissionDenied):
            await asyncio.wait_for(uploads.service.put(caller(), upload.id, "application/octet-stream", data()), 5)
    with pytest.raises(PermissionDenied):
        await uploads.service.complete(caller(), upload.id)
    assert await uploads.content.namespace.list_children(ROOT_ID) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("size,payload,error", [(3, b"ab", UploadLengthMismatch), (3, b"abcd", UploadTooLarge)])
async def test_failed_length_check_can_retry_full_transfer(
    uploads: UploadContext, size: int, payload: bytes, error: type[Exception],
) -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "retry", metadata(), size)
    with pytest.raises(error):
        await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(payload))
    assert (await uploads.service.get(caller(), upload.id)).progress.status == "pending"
    await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"x" * size))
    assert (await uploads.service.complete(caller(), upload.id)).created


@pytest.mark.asyncio
async def test_declared_limit_and_premature_completion(uploads: UploadContext) -> None:
    with pytest.raises(UploadTooLarge):
        await uploads.service.begin(caller(), ROOT_ID, "large", metadata(), 7)
    upload = await uploads.service.begin(caller(), ROOT_ID, "early", metadata(), 0)
    with pytest.raises(UploadConflict):
        await uploads.service.complete(caller(), upload.id)


@pytest.mark.asyncio
async def test_interrupted_transfer_can_retry(uploads: UploadContext) -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "retry", metadata(), 2)

    async def interrupted() -> ByteStream:
        yield b"a"
        raise ConnectionError("interrupted")

    with pytest.raises(ConnectionError):
        await uploads.service.put(caller(), upload.id, "application/octet-stream", interrupted())
    await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"ok"))
    assert (await uploads.service.complete(caller(), upload.id)).created


@pytest.mark.asyncio
@pytest.mark.parametrize("uploaded", [False, True])
async def test_expired_incomplete_sessions_are_gone(uploads: UploadContext, uploaded: bool) -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "expired", metadata(), 1)
    if uploaded:
        await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))
    uploads.clock.current += timedelta(hours=1)
    with pytest.raises(UploadExpired):
        await uploads.service.get(caller(), upload.id)
    with pytest.raises(UploadExpired):
        await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))
    with pytest.raises(UploadExpired):
        await uploads.service.complete(caller(), upload.id)


@pytest.mark.asyncio
async def test_concurrent_completion_is_idempotent_and_completed_content_is_immutable(uploads: UploadContext) -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "once", metadata(), 1)
    await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))
    results = await asyncio.gather(*(uploads.service.complete(caller(), upload.id) for _ in range(5)))
    assert sum(result.created for result in results) == 1
    assert all(result.node == results[0].node for result in results)
    uploads.clock.current += timedelta(days=1)
    assert (await uploads.service.get(caller(), upload.id)).progress.status == "completed"
    assert (await uploads.service.complete(caller(), upload.id)).node == results[0].node
    with pytest.raises(UploadConflict):
        await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"y"))
    download = await uploads.content.service.open_download(caller(), results[0].node.id)
    assert b"".join([chunk async for chunk in download.data]) == b"x"


@pytest.mark.asyncio
async def test_completion_rechecks_current_size_limit_without_changing_completed_outcomes(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    completed = await uploads.service.begin(caller(), ROOT_ID, "completed", metadata(), 6)
    staged = await uploads.service.begin(caller(), ROOT_ID, "staged", metadata(), 6)
    for upload in (completed, staged):
        await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"abcdef"))
    result = await uploads.service.complete(caller(), completed.id)
    restricted = UploadService(
        VerifiedIdentityResolver(), DatabaseUploadTransactions(filesystem_runtime.database),
        uploads.content.content, 3, uploads.clock, timedelta(hours=1),
    )
    with pytest.raises(UploadTooLarge):
        await restricted.complete(caller(), staged.id)
    assert (await restricted.get(caller(), staged.id)).progress.status == "uploaded"
    assert (await restricted.complete(caller(), completed.id)).node == result.node
    assert [node.id for node in await uploads.content.namespace.list_children(ROOT_ID)] == [result.node.id]


@pytest.mark.asyncio
async def test_inflight_transfer_cannot_replace_content_published_by_completion(uploads: UploadContext) -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "racing", metadata(), 1)
    await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))

    async def racing() -> ByteStream:
        await uploads.service.complete(caller(), upload.id)
        yield b"y"

    with pytest.raises(UploadConflict):
        await uploads.service.put(caller(), upload.id, "application/octet-stream", racing())
    result = await uploads.service.complete(caller(), upload.id)
    download = await uploads.content.service.open_download(caller(), result.node.id)
    assert b"".join([chunk async for chunk in download.data]) == b"x"


class IncorrectSizeContent:
    def __init__(self, content: ContentDriver) -> None:
        self._content = content

    async def put(self, data: ByteStream) -> ContentRef:
        content = await self._content.put(data)
        return ContentRef(key=content.key, size=content.size + 1)

    async def get(self, key: StorageKey) -> ByteStream:
        async for chunk in self._content.get(key):
            yield chunk


@pytest.mark.asyncio
async def test_storage_size_mismatch_cannot_be_staged(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    service = UploadService(
        VerifiedIdentityResolver(), DatabaseUploadTransactions(filesystem_runtime.database),
        IncorrectSizeContent(uploads.content.content), 6, uploads.clock, timedelta(hours=1),
    )
    upload = await service.begin(caller(), ROOT_ID, "mismatched", metadata(), 1)
    with pytest.raises(UploadLengthMismatch):
        await service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))
    assert (await service.get(caller(), upload.id)).progress.status == "pending"
    with pytest.raises(UploadConflict):
        await service.complete(caller(), upload.id)
    assert await uploads.content.namespace.list_children(ROOT_ID) == []


class FailOnceContent:
    def __init__(self, content: ContentDriver) -> None:
        self._content = content
        self._failed = False

    async def put(self, data: ByteStream) -> ContentRef:
        if not self._failed:
            self._failed = True
            raise StorageFailure("Content unavailable")
        return await self._content.put(data)

    async def get(self, key: StorageKey) -> ByteStream:
        async for chunk in self._content.get(key):
            yield chunk


@pytest.mark.asyncio
async def test_storage_failure_allows_full_transfer_retry(uploads: UploadContext, filesystem_runtime: PersistenceRuntime) -> None:
    service = UploadService(
        VerifiedIdentityResolver(), DatabaseUploadTransactions(filesystem_runtime.database),
        FailOnceContent(uploads.content.content), 6, uploads.clock, timedelta(hours=1),
    )
    upload = await service.begin(caller(), ROOT_ID, "retry-storage", metadata(), 1)
    with pytest.raises(StorageFailure):
        await service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))
    assert (await service.get(caller(), upload.id)).progress.status == "pending"
    await service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))
    assert (await service.complete(caller(), upload.id)).created


class FailingCompletionStore:
    def __init__(self, store: UploadStore) -> None:
        self._store = store

    async def get(self, upload_id: UUID) -> Optional[UploadSession]:
        return await self._store.get(upload_id)

    async def save(self, upload: UploadSession) -> None:
        raise StorageFailure("Completion persistence failed")


class FailingCompletionTransactions:
    def __init__(self, transactions: UploadTransactions) -> None:
        self._transactions = transactions

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[UploadTransaction]:
        async with self._transactions.transaction() as session:
            yield UploadTransaction(
                namespace=session.namespace, access_control=session.access_control,
                uploads=FailingCompletionStore(session.uploads),
            )


@pytest.mark.asyncio
async def test_failed_session_transition_rolls_back_node_owner_and_reference(
    uploads: UploadContext, filesystem_runtime: PersistenceRuntime,
) -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "rollback", metadata(), 1)
    await uploads.service.put(caller(), upload.id, "application/octet-stream", stream(b"x"))
    failing = UploadService(
        VerifiedIdentityResolver(), FailingCompletionTransactions(DatabaseUploadTransactions(filesystem_runtime.database)),
        uploads.content.content, 6, uploads.clock, timedelta(hours=1),
    )
    with pytest.raises(StorageFailure):
        await failing.complete(caller(), upload.id)
    assert await uploads.content.namespace.list_children(ROOT_ID) == []
    assert (await uploads.service.get(caller(), upload.id)).progress.status == "uploaded"
    result = await uploads.service.complete(caller(), upload.id)
    assert (await uploads.content.policies.get_owner(result.node.id)).owner == alice()


@pytest.mark.asyncio
async def test_expiry_during_transfer_does_not_publish_staged_reference(uploads: UploadContext) -> None:
    upload = await uploads.service.begin(caller(), ROOT_ID, "expires", metadata(), 1)

    async def delayed() -> ByteStream:
        uploads.clock.current += timedelta(hours=1)
        yield b"x"

    with pytest.raises(UploadExpired):
        await uploads.service.put(caller(), upload.id, "application/octet-stream", delayed())
    assert await uploads.content.namespace.list_children(ROOT_ID) == []


@pytest.mark.asyncio
async def test_sqlite_restart_recovers_pending_uploaded_and_completed_sessions(tmp_path: Path) -> None:
    path = tmp_path / "uploads.sqlite"
    config = LocalContentConfig(type="local", directory=tmp_path / "content")
    clock = Clock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    runtime = await prepared_sqlite_runtime(path)
    await create_root_provisioning(database=runtime.database).provision(RootBootstrapSpec(grants=(
        RootBootstrapGrant(principal=alice(), permissions=frozenset({Permission.DISCOVER, Permission.WRITE})),
    )))
    service = UploadService(VerifiedIdentityResolver(), DatabaseUploadTransactions(runtime.database),
                            create_content_driver(config), 6, clock, timedelta(hours=1))
    pending = await service.begin(caller(), ROOT_ID, "pending", metadata(), 1)
    uploaded = await service.begin(caller(), ROOT_ID, "uploaded", metadata(), 1)
    await service.put(caller(), uploaded.id, "application/octet-stream", stream(b"x"))
    await runtime.shutdown()
    runtime = await prepared_sqlite_runtime(path)
    try:
        content = create_content_driver(config)
        service = UploadService(VerifiedIdentityResolver(), DatabaseUploadTransactions(runtime.database), content, 6, clock, timedelta(hours=1))
        assert (await service.get(caller(), pending.id)).progress.status == "pending"
        assert (await service.get(caller(), uploaded.id)).progress.status == "uploaded"
        result = await service.complete(caller(), uploaded.id)
    finally:
        await runtime.shutdown()
    runtime = await prepared_sqlite_runtime(path)
    try:
        content = create_content_driver(config)
        service = UploadService(VerifiedIdentityResolver(), DatabaseUploadTransactions(runtime.database), content, 6, clock, timedelta(hours=1))
        assert not (await service.complete(caller(), uploaded.id)).created
        assert (await service.complete(caller(), uploaded.id)).node == result.node
        download = await ContentService(VerifiedIdentityResolver(), create_filesystem_transactions(database=runtime.database),
                                        content, 6).open_download(caller(), result.node.id)
        assert b"".join([chunk async for chunk in download.data]) == b"x"
        assert len(await create_namespace_driver(database=runtime.database).list_children(ROOT_ID)) == 1
    finally:
        await runtime.shutdown()
