from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from umbod.core.filesystem import AccessGrant, ContentRef, NodeKind, NodeMetadata, Ownership, Permission, Principal, PrincipalType
from umbod.core.filesystem.namespace import initial_root, new_node, updated_node
from umbod.core.filesystem.stores.namespace import node_record
from umbod.core.filesystem.stores.schema import GRANT_TABLE, NODE_ID, NODE_TABLE, OWNER_TABLE, GrantRecord, OwnershipRecord
from umbod.core.persistence import AllFields, InsertCommand, NoFilter, OrderBy, Query, TransactionMode, Unordered
from umbod.core.publishing.stores.schema import PUBLICATION_STATE_TABLE, PublicationStateRecord
from umbod.infrastructure.filesystem.local_content import LocalContent
from tests.persistence_runtime import prepared_sqlite_runtime


async def stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


@pytest.mark.asyncio
async def test_sqlite_filesystem_records_and_local_content_survive_runtime_recreation(tmp_path: Path) -> None:
    path = tmp_path / "records.sqlite"
    content_path = tmp_path / "content"
    content = LocalContent(content_path)
    reference = await content.put(stream(b"persisted\x00bytes"))
    root = initial_root()
    metadata = NodeMetadata(content_type="text/plain", attributes={"team": "research"})
    directory = new_node(root.id, "Reports", NodeKind.DIRECTORY, metadata)
    file = new_node(directory.id, "Résumé.txt", NodeKind.FILE, metadata)
    written = updated_node(file, reference, file.revision)
    nodes = tuple(node_record(node) for node in (root, directory, written))
    owner = OwnershipRecord(
        node_id=str(file.id),
        payload=Ownership(node_id=file.id, owner=Principal(type=PrincipalType.USER, issuer="provider", id="owner")),
    )
    grant = GrantRecord(
        node_id=str(file.id), principal_type="user", issuer="provider", principal_id="reader",
        payload=AccessGrant(
            node_id=file.id, principal=Principal(type=PrincipalType.USER, issuer="provider", id="reader"),
            permissions={Permission.READ}, recursive=True,
        ),
    )
    publication = PublicationStateRecord(
        connector_id="neighbor", published=True, previously_published=True,
        revision=4, updated_at="2026-01-01T00:00:00+00:00",
    )
    runtime = await prepared_sqlite_runtime(path)
    try:
        async with runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            for node in nodes:
                assert await session.insert(NODE_TABLE, InsertCommand(row=node))
            assert await session.insert(OWNER_TABLE, InsertCommand(row=owner))
            assert await session.insert(GRANT_TABLE, InsertCommand(row=grant))
            assert await session.insert(PUBLICATION_STATE_TABLE, InsertCommand(row=publication))
    finally:
        await runtime.shutdown()
    reopened = await prepared_sqlite_runtime(path)
    try:
        async with reopened.database.read_session() as session:
            restored_nodes = await session.find_many(NODE_TABLE, Query(NoFilter(), AllFields(), OrderBy((NODE_ID,))))
            assert restored_nodes == tuple(sorted(nodes, key=lambda node: node.node_id))
            assert await session.find_many(OWNER_TABLE, Query(NoFilter(), AllFields(), Unordered())) == (owner,)
            assert await session.find_many(GRANT_TABLE, Query(NoFilter(), AllFields(), Unordered())) == (grant,)
            assert await session.find_many(PUBLICATION_STATE_TABLE, Query(NoFilter(), AllFields(), Unordered())) == (publication,)
        restored_file = next(record.payload for record in restored_nodes if record.node_id == str(file.id))
        assert isinstance(restored_file.content, ContentRef)
        restored_content = LocalContent(content_path)
        assert b"".join([chunk async for chunk in restored_content.get(restored_file.content.key)]) == b"persisted\x00bytes"
    finally:
        await reopened.shutdown()
