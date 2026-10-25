import asyncio
import multiprocessing
from collections.abc import AsyncIterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from pydantic import BaseModel

from umbod.core.filesystem import (
    AccessGrant,
    ContentRef,
    NodeKind,
    NodeMetadata,
    Ownership,
    OwnershipNotFound,
    Permission,
    Principal,
    PrincipalType,
    StorageFailure,
    NameCollision,
    Node,
    RevisionConflict,
)
from umbod.core.filesystem.stores.schema import NODE_TABLE, NodeKey, NodeRecord
from umbod.core.persistence import (
    Database,
    DatabaseSession,
    PersistenceRuntime,
    Table,
    TransactionMode,
    UpsertCommand,
)
from umbod.core.publishing.factories import create_connector_publishing_store
from umbod.infrastructure import (
    FilesystemConfig,
    LocalContentConfig,
    create_access_control_driver,
    create_filesystem,
    create_namespace_driver,
)
from tests.persistence_runtime import create_sqlite_runtime, prepared_sqlite_runtime
from tests.support.filesystem.processes import create_database_child_in_process


def metadata() -> NodeMetadata:
    return NodeMetadata(content_type="text/plain", attributes={"team": "research"})


def subject(identifier: str) -> Principal:
    return Principal(type=PrincipalType.USER, issuer="provider", id=identifier)


async def stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


@pytest.mark.asyncio
async def test_sqlite_reopen_preserves_namespace_bytes_and_policies_with_neighboring_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shared.db"
    config = FilesystemConfig(
        content=LocalContentConfig(type="local", directory=tmp_path / "content")
    )
    runtime = await prepared_sqlite_runtime(path)
    try:
        filesystem = create_filesystem(config, database=runtime.database)
        root = await filesystem.get_root()
        directory = await filesystem.create_directory(root.id, "Reports", metadata())
        file = await filesystem.create_file(directory.id, "Résumé.txt", metadata())
        written = await filesystem.write(
            file.id, stream(b"persisted\x00bytes"), expected_revision=file.revision
        )
        policies = create_access_control_driver(database=runtime.database)
        owner = Ownership(node_id=file.id, owner=subject("owner"))
        grant = AccessGrant(
            node_id=file.id,
            principal=subject("reader"),
            permissions={Permission.READ},
            recursive=True,
        )
        await policies.set_owner(owner)
        await policies.add_grant(grant)
        publishing = await create_connector_publishing_store(runtime.database)
        await publishing.publish_connector("neighbor")
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        filesystem = create_filesystem(config, database=reopened.database)
        policies = create_access_control_driver(database=reopened.database)
        assert await filesystem.get_root() == root
        assert tuple(await filesystem.list_children(root.id)) == (directory,)
        assert await filesystem.get_node(file.id) == written
        assert (
            b"".join([chunk async for chunk in filesystem.read(file.id)])
            == b"persisted\x00bytes"
        )
        assert await policies.get_owner(file.id) == owner
        assert tuple(await policies.list_grants(file.id)) == (grant,)
        publishing = await create_connector_publishing_store(reopened.database)
        assert await publishing.is_published("neighbor")
    finally:
        await reopened.shutdown()


@pytest.mark.asyncio
async def test_separate_processes_initialize_one_root_and_preserve_all_creations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "processes.db"
    schema_runtime = await prepared_sqlite_runtime(path)
    await schema_runtime.shutdown()
    names = tuple(f"child-{index}" for index in range(8))
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(
        max_workers=2, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        roots = await asyncio.gather(
            *(
                loop.run_in_executor(pool, create_database_child_in_process, path, name)
                for name in names
            )
        )
    runtime = await prepared_sqlite_runtime(path)
    try:
        namespace = create_namespace_driver(database=runtime.database)
        root = await namespace.get_root()
        assert set(roots) == {str(root.id)}
        assert {node.name for node in await namespace.list_children(root.id)} == set(
            names
        )
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_independent_sqlite_runtime_conflicts_preserve_winning_mutations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "conflicts.db"
    first_runtime = await prepared_sqlite_runtime(path)
    second_runtime = await prepared_sqlite_runtime(path)
    try:
        first = create_namespace_driver(database=first_runtime.database)
        second = create_namespace_driver(database=second_runtime.database)
        roots = await asyncio.gather(first.get_root(), second.get_root())
        assert roots[0] == roots[1]
        root = roots[0]
        creations = await asyncio.gather(
            first.create_node(root.id, "same", NodeKind.FILE, metadata()),
            second.create_node(root.id, "same", NodeKind.FILE, metadata()),
            return_exceptions=True,
        )
        winners = [result for result in creations if isinstance(result, Node)]
        assert len(winners) == 1
        assert sum(isinstance(result, NameCollision) for result in creations) == 1
        file = winners[0]
        publications = await asyncio.gather(
            first.update_node(
                file.id,
                content=ContentRef(key="a" * 32, size=1),
                expected_revision=file.revision,
            ),
            second.update_node(
                file.id,
                content=ContentRef(key="b" * 32, size=2),
                expected_revision=file.revision,
            ),
            return_exceptions=True,
        )
        published = [result for result in publications if isinstance(result, Node)]
        assert len(published) == 1
        assert sum(isinstance(result, RevisionConflict) for result in publications) == 1
        assert await second.get_node(file.id) == published[0]
        assert tuple(await first.list_children(root.id)) == (published[0],)
    finally:
        await first_runtime.shutdown()
        await second_runtime.shutdown()


@pytest.mark.asyncio
async def test_invalid_persisted_node_is_reported_as_storage_failure(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    database = filesystem_runtime.database
    namespace = create_namespace_driver(database=database)
    root = await namespace.get_root()
    child = await namespace.create_node(root.id, "retained", NodeKind.FILE, metadata())
    corrupt = NodeRecord.model_construct(
        node_id=str(root.id),
        parent_id="",
        name="invalid-index",
        revision=root.revision,
        payload=root,
    )
    async with database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await session.upsert(
            NODE_TABLE, UpsertCommand(key=NodeKey(node_id=str(root.id)), row=corrupt)
        )
    with pytest.raises(StorageFailure):
        await namespace.get_root()
    assert await namespace.get_node(child.id) == child


class FailingCommitDatabase:
    def __init__(self, database: Database, cancelled: bool) -> None:
        self._database = database
        self._cancelled = cancelled

    async def ensure_schema(
        self, tables: Sequence[Table[BaseModel, BaseModel]]
    ) -> None:
        await self._database.ensure_schema(tables)

    @asynccontextmanager
    async def session(self, *, mode: TransactionMode) -> AsyncIterator[DatabaseSession]:
        assert mode == TransactionMode.SERIALIZED_WRITE
        async with self._database.session(mode=mode) as session:
            yield session
            if self._cancelled:
                raise asyncio.CancelledError()
            raise RuntimeError("injected transaction failure")


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_failed_publication_rolls_back_without_touching_other_rows(
    filesystem_runtime: PersistenceRuntime, cancelled: bool
) -> None:
    database = filesystem_runtime.database
    namespace = create_namespace_driver(database=database)
    root = await namespace.get_root()
    file = await namespace.create_node(root.id, "retained", NodeKind.FILE, metadata())
    broken = create_namespace_driver(
        database=FailingCommitDatabase(database, cancelled)
    )
    expected_error = asyncio.CancelledError if cancelled else StorageFailure
    with pytest.raises(expected_error):
        await broken.update_node(
            file.id,
            content=ContentRef(key="a" * 32, size=3),
            expected_revision=file.revision,
        )
    with pytest.raises(expected_error):
        await broken.create_node(root.id, "unpublished", NodeKind.FILE, metadata())
    assert await namespace.get_node(file.id) == file
    assert tuple(await namespace.list_children(root.id)) == (file,)


@pytest.mark.asyncio
async def test_failed_policy_replacements_preserve_previous_records(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    namespace = create_namespace_driver(database=filesystem_runtime.database)
    root = await namespace.get_root()
    policies = create_access_control_driver(database=filesystem_runtime.database)
    owner = Ownership(node_id=root.id, owner=subject("owner"))
    grant = AccessGrant(
        node_id=root.id,
        principal=subject("reader"),
        permissions={Permission.READ},
        recursive=False,
    )
    await policies.set_owner(owner)
    await policies.add_grant(grant)
    broken = create_access_control_driver(
        database=FailingCommitDatabase(filesystem_runtime.database, False)
    )
    with pytest.raises(StorageFailure):
        await broken.set_owner(
            Ownership(node_id=root.id, owner=subject("replacement"))
        )
    with pytest.raises(StorageFailure):
        await broken.add_grant(
            grant.model_copy(update={"permissions": set(), "recursive": True})
        )
    with pytest.raises(StorageFailure):
        await broken.remove_grant(root.id, grant.principal)
    assert await policies.get_owner(root.id) == owner
    assert tuple(await policies.list_grants(root.id)) == (grant,)


@pytest.mark.asyncio
async def test_application_readiness_prepares_filesystem_without_constructor_io(
    tmp_path: Path,
) -> None:
    runtime = create_sqlite_runtime(tmp_path / "readiness.db")
    try:
        namespace = create_namespace_driver(database=runtime.database)
        policies = create_access_control_driver(database=runtime.database)
        with pytest.raises(StorageFailure):
            await namespace.get_root()
        await runtime.readiness.ensure_ready()
        root = await namespace.get_root()
        with pytest.raises(OwnershipNotFound):
            await policies.get_owner(root.id)
        assert tuple(await policies.list_grants(root.id)) == ()
    finally:
        await runtime.shutdown()
