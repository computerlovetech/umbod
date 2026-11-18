import asyncio
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest

from tests.persistence_runtime import prepared_sqlite_runtime
from tests.umbod.core.filesystem.test_authorized_content import metadata, stream
from tests.umbod.core.filesystem.test_verified_identity import snapshot
from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem import AccessGrant, NodeKind, Permission, StorageFailure
from umbod.core.filesystem.authorization import PermissionDenied, VerifiedIdentityResolver
from umbod.core.filesystem.deletion import DeletionService
from umbod.core.filesystem.errors import MissingNode, OwnershipNotFound
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.namespaces import CreateSharedNamespace, DeleteSharedNamespace, NamespaceGroupAccess, SharedNamespaceView
from umbod.core.filesystem.namespaces.errors import NamespaceActiveUploads, NamespaceNotEmpty
from umbod.core.filesystem.stores.uploads import DatabaseUploadTransactions
from umbod.core.filesystem.uploads.models import ClaimedTransfer, DelegatedTransfer, ExternalTransfer, UploadedContent, UploadSession
from umbod.core.filesystem.uploads.service import SystemUploadClock
from umbod.core.groups.models import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.persistence import Database, DatabaseSession, TransactionMode
from umbod.infrastructure import (
    InMemoryContentConfig, create_access_control_driver, create_content_driver, create_filesystem_creation,
    create_filesystem_namespace_management, create_filesystem_transactions, create_filesystem_uploads, create_namespace_driver,
)


CALLER = snapshot("alice", "issuer", ("team",))
IN_MEMORY_CONTENT = InMemoryContentConfig(type="inmemory")


async def create_shared(database: Database, name: str = "Shared") -> SharedNamespaceView:
    await create_group_management(database).register_group(RegisterGroup(group_id="team"))
    return await create_filesystem_namespace_management(database=database, issuer="issuer").create(CreateSharedNamespace(
        name=name, groups=[NamespaceGroupAccess(group_id="team", access="read_write")],
    ))


async def delete_shared(database: Database, view: SharedNamespaceView) -> None:
    await create_filesystem_namespace_management(database=database, issuer="issuer").delete(
        view.id, DeleteSharedNamespace(expected_revision=view.revision, expected_root_revision=view.root_revision),
    )


async def record_upload(database: Database, upload: UploadSession) -> None:
    async with DatabaseUploadTransactions(database).transaction() as transaction:
        await transaction.uploads.save(upload)


async def stored_upload(database: Database, upload_id: UUID) -> UploadSession | None:
    async with DatabaseUploadTransactions(database).transaction() as transaction:
        return await transaction.uploads.get(upload_id)


@pytest.mark.asyncio
async def test_delete_preserves_upload_history_content_wrapper_and_other_namespace(tmp_path: Path) -> None:
    runtime = await prepared_sqlite_runtime(tmp_path / "filesystem.sqlite")
    database = runtime.database
    resolver = VerifiedIdentityResolver()
    content = create_content_driver(IN_MEMORY_CONTENT)
    uploads = create_filesystem_uploads(
        database=database, resolver=resolver, content=content, max_upload_bytes=10, clock=SystemUploadClock(),
    )
    nodes = create_namespace_driver(database=database)
    access = create_access_control_driver(database=database)
    try:
        target = await create_shared(database)
        other = await create_shared(database, "Other")
        root = await nodes.get_node(target.root_node_id)
        assert isinstance(root.parent_id, UUID)
        wrapper = await nodes.get_node(root.parent_id)
        identity = await resolver.resolve(CALLER)
        await access.add_grant(AccessGrant(
            node_id=root.id, principal=identity.user, permissions={Permission.DISCOVER}, recursive=False,
        ))
        completed = await uploads.begin(CALLER, root.id, "file", metadata(), 3)
        await uploads.put(CALLER, completed.id, "application/octet-stream", stream(b"abc"))
        staged = await uploads.get(CALLER, completed.id)
        assert isinstance(staged.progress, UploadedContent)
        publication = await uploads.complete(CALLER, completed.id)
        await DeletionService(resolver, create_filesystem_transactions(database=database)).delete_file(
            CALLER, publication.node.id, expected_revision=publication.node.revision,
        )
        history = await uploads.get(CALLER, completed.id)
        expired = staged.model_copy(update={"id": uuid4(), "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
        await record_upload(database, expired)
        other_upload = await uploads.begin(CALLER, other.root_node_id, "keep", metadata(), 0)

        await delete_shared(database, target)

        management = create_filesystem_namespace_management(database=database, issuer="issuer")
        assert await management.list() == [other]
        with pytest.raises(MissingNode):
            await nodes.get_node(root.id)
        with pytest.raises(OwnershipNotFound):
            await access.get_owner(root.id)
        assert await access.list_grants(root.id) == []
        assert await nodes.get_node(wrapper.id) == wrapper
        assert (await nodes.get_root()).id == ROOT_ID
        assert await stored_upload(database, completed.id) == history
        assert await stored_upload(database, expired.id) == expired
        for upload_id in (history.id, expired.id):
            with pytest.raises(PermissionDenied):
                await uploads.complete(CALLER, upload_id)
        assert await uploads.get(CALLER, other_upload.id) == other_upload
        assert b"".join([chunk async for chunk in content.get(staged.progress.content.key)]) == b"abc"
        await management.create(CreateSharedNamespace(name="Still assigned", groups=other.groups))
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_sqlite_delete_rolls_back_policy_node_and_acl_if_cleanup_fails(tmp_path: Path) -> None:
    path = tmp_path / "filesystem.sqlite"
    runtime = await prepared_sqlite_runtime(path)
    database = runtime.database
    try:
        target = await create_shared(database)
        nodes = create_namespace_driver(database=database)
        root = await nodes.get_node(target.root_node_id)
        access = create_access_control_driver(database=database)
        identity = await VerifiedIdentityResolver().resolve(CALLER)
        grant = AccessGrant(node_id=root.id, principal=identity.user, permissions={Permission.DISCOVER}, recursive=False)
        await access.add_grant(grant)
        owner = await access.get_owner(root.id)
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_namespace_cleanup BEFORE DELETE ON filesystem_ownership "
                "BEGIN SELECT RAISE(ABORT, 'test cleanup failure'); END"
            )

        with pytest.raises(StorageFailure):
            await delete_shared(database, target)

        assert await create_filesystem_namespace_management(database=database, issuer="issuer").list() == [target]
        assert await nodes.get_node(root.id) == root
        assert await access.get_owner(root.id) == owner
        assert await access.list_grants(root.id) == [grant]
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "claimed", "uploaded", "expired-capability"])
async def test_live_upload_sessions_block_namespace_deletion(tmp_path: Path, state: str) -> None:
    runtime = await prepared_sqlite_runtime(tmp_path / "filesystem.sqlite")
    database = runtime.database
    resolver = VerifiedIdentityResolver()
    uploads = create_filesystem_uploads(
        database=database, resolver=resolver, content=create_content_driver(IN_MEMORY_CONTENT),
        max_upload_bytes=10, clock=SystemUploadClock(),
    )
    try:
        target = await create_shared(database)
        upload = await uploads.begin(CALLER, target.root_node_id, "file", metadata(), 1)
        if state in {"uploaded", "expired-capability"}:
            await uploads.put(CALLER, upload.id, "application/octet-stream", stream(b"x"))
            upload = await uploads.get(CALLER, upload.id)
        if state == "claimed":
            transfer = DelegatedTransfer(
                token_digest="0" * 64, identity=await resolver.resolve(CALLER),
                expires_at=upload.expires_at, state=ClaimedTransfer(claim_id=uuid4()),
            )
            upload = upload.model_copy(update={"delegated_transfer": transfer})
        if state == "expired-capability":
            upload = upload.model_copy(update={"delegated_transfer": ExternalTransfer(
                storage_key="0" * 32, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            )})
        await record_upload(database, upload)

        with pytest.raises(NamespaceActiveUploads):
            await delete_shared(database, target)

        assert await stored_upload(database, upload.id) == upload
        assert await create_filesystem_namespace_management(database=database, issuer="issuer").list() == [target]
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["child", "begin", "publish"])
@pytest.mark.parametrize("delete_first", [True, False])
async def test_namespace_delete_serializes_with_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: Literal["child", "begin", "publish"], delete_first: bool,
) -> None:
    path = tmp_path / "filesystem.sqlite"
    first = await prepared_sqlite_runtime(path)
    second = await prepared_sqlite_runtime(path)
    writer_db, delete_db = (second.database, first.database) if delete_first else (first.database, second.database)
    resolver = VerifiedIdentityResolver()
    uploads = create_filesystem_uploads(
        database=writer_db, resolver=resolver, content=create_content_driver(IN_MEMORY_CONTENT),
        max_upload_bytes=10, clock=SystemUploadClock(),
    )
    creation = create_filesystem_creation(database=writer_db, resolver=resolver)
    acquired = asyncio.Event()
    attempting = asyncio.Event()
    first_session, second_session = first.database.session, second.database.session
    upload_lookup = uploads.get
    looking_up_upload = False

    async def lookup_before_publication(caller: CallerSnapshot, upload_id: UUID) -> UploadSession:
        nonlocal looking_up_upload
        looking_up_upload = True
        try:
            return await upload_lookup(caller, upload_id)
        finally:
            looking_up_upload = False

    @asynccontextmanager
    async def hold_first(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        async with first_session(mode=mode) as session:
            if not looking_up_upload:
                acquired.set()
                await attempting.wait()
            yield session

    @asynccontextmanager
    async def signal_second(*, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        attempting.set()
        async with second_session(mode=mode) as session:
            yield session

    try:
        target = await create_shared(delete_db)
        if operation == "publish":
            staged = await uploads.begin(CALLER, target.root_node_id, "file", metadata(), 1)
            await uploads.put(CALLER, staged.id, "application/octet-stream", stream(b"x"))

        async def write() -> None:
            if operation == "child":
                await creation.create_directory(CALLER, target.root_node_id, "child", metadata())
            elif operation == "begin":
                await uploads.begin(CALLER, target.root_node_id, "file", metadata(), 0)
            else:
                await uploads.complete(CALLER, staged.id)

        async def delete() -> None:
            await delete_shared(delete_db, target)

        earlier, later = (delete, write) if delete_first else (write, delete)
        if operation == "publish" and not delete_first:
            monkeypatch.setattr(uploads, "get", lookup_before_publication)
        monkeypatch.setattr(first.database, "session", hold_first)
        monkeypatch.setattr(second.database, "session", signal_second)

        async def contend(action: Callable[[], Awaitable[None]]) -> None:
            await acquired.wait()
            await action()

        outcomes = await asyncio.wait_for(asyncio.gather(earlier(), contend(later), return_exceptions=True), timeout=10)
        nodes = create_namespace_driver(database=delete_db)
        if delete_first and operation != "publish":
            assert outcomes[0] is None
            assert isinstance(outcomes[1], PermissionDenied)
            with pytest.raises(MissingNode):
                await nodes.get_node(target.root_node_id)
        else:
            blocker = NamespaceActiveUploads if operation == "begin" or delete_first else NamespaceNotEmpty
            deletion_outcome, writer_outcome = outcomes if delete_first else outcomes[::-1]
            assert writer_outcome is None
            assert isinstance(deletion_outcome, blocker)
            assert (await nodes.get_node(target.root_node_id)).kind == NodeKind.DIRECTORY
    finally:
        await second.shutdown()
        await first.shutdown()
