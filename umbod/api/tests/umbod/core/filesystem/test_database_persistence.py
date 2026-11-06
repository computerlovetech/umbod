import asyncio
from collections.abc import AsyncIterator, Sequence
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
    ReadSession,
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


def metadata() -> NodeMetadata:
    return NodeMetadata(content_type="text/plain", attributes={"team": "research"})


def subject(identifier: str) -> Principal:
    return Principal(type=PrincipalType.USER, issuer="provider", id=identifier)


async def stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


@pytest.mark.asyncio
async def test_service_recreation_preserves_namespace_bytes_and_policies_with_neighboring_data(
    filesystem_runtime: PersistenceRuntime, tmp_path: Path,
) -> None:
    database = filesystem_runtime.database
    config = FilesystemConfig(
        content=LocalContentConfig(type="local", directory=tmp_path / "content")
    )
    filesystem = create_filesystem(config, database=database)
    root = await filesystem.get_root()
    directory = await filesystem.create_directory(root.id, "Reports", metadata())
    file = await filesystem.create_file(directory.id, "Résumé.txt", metadata())
    written = await filesystem.write(
        file.id, stream(b"persisted\x00bytes"), expected_revision=file.revision
    )
    policies = create_access_control_driver(database=database)
    owner = Ownership(node_id=file.id, owner=subject("owner"))
    grant = AccessGrant(
        node_id=file.id,
        principal=subject("reader"),
        permissions={Permission.READ},
        recursive=True,
    )
    await policies.set_owner(owner)
    await policies.add_grant(grant)
    publishing = await create_connector_publishing_store(database)
    await publishing.publish_connector("neighbor")
    filesystem = create_filesystem(config, database=database)
    policies = create_access_control_driver(database=database)
    assert await filesystem.get_root() == root
    assert tuple(await filesystem.list_children(root.id)) == (directory,)
    assert await filesystem.get_node(file.id) == written
    assert (
        b"".join([chunk async for chunk in filesystem.read(file.id)])
        == b"persisted\x00bytes"
    )
    assert await policies.get_owner(file.id) == owner
    assert tuple(await policies.list_grants(file.id)) == (grant,)
    publishing = await create_connector_publishing_store(database)
    assert await publishing.is_published("neighbor")


@pytest.mark.asyncio
async def test_independent_services_initialize_one_root_and_preserve_all_creations(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    names = tuple(f"child-{index}" for index in range(8))

    async def create_child(name: str) -> str:
        namespace = create_namespace_driver(database=filesystem_runtime.database)
        root = await namespace.get_root()
        await namespace.create_node(root.id, name, NodeKind.FILE, metadata())
        return str(root.id)

    roots = await asyncio.gather(*(create_child(name) for name in names))
    namespace = create_namespace_driver(database=filesystem_runtime.database)
    root = await namespace.get_root()
    assert set(roots) == {str(root.id)}
    assert {node.name for node in await namespace.list_children(root.id)} == set(
        names
    )


@pytest.mark.asyncio
async def test_independent_services_preserve_winning_mutations_on_conflict(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    first = create_namespace_driver(database=filesystem_runtime.database)
    second = create_namespace_driver(database=filesystem_runtime.database)
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
    async def read_session(self) -> AsyncIterator[ReadSession]:
        async with self._database.read_session() as session:
            yield session

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
