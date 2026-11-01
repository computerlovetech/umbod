from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio

from umbod.core.filesystem.authorization import FILESYSTEM_DISCOVERY_CHANGED
from umbod.core.filesystem.models import (
    AccessGrant, ContentRef, NodeKind, NodeMetadata, Ownership, Permission,
    Principal, PrincipalType, UnspecifiedContentType,
)
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.stores import (
    DatabaseAccessControl, DatabaseFilesystemAuthorizationReader, DatabaseNamespace,
)
from umbod.core.filesystem.stores.access_control import SessionAccessControl
from umbod.core.filesystem.stores.namespace import SessionNamespace
from umbod.core.filesystem.stores.sharing import DatabaseSharingTransactions
from umbod.core.messaging.stores.event_stream import DatabaseEventStream
from umbod.core.persistence import Database, PersistenceRuntime, ReadSession, TransactionMode
from tests.persistence_runtime import prepared_inmemory_runtime


@pytest_asyncio.fixture
async def event_runtime() -> AsyncIterator[PersistenceRuntime]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime
    finally:
        await runtime.shutdown()


def subject() -> Principal:
    return Principal(type=PrincipalType.USER, issuer="private-issuer", id="private-user")


def metadata() -> NodeMetadata:
    return NodeMetadata(content_type=UnspecifiedContentType(), attributes={})


@pytest.mark.asyncio
async def test_namespace_creation_and_deletion_emit_sanitized_events_but_content_does_not(
    event_runtime: PersistenceRuntime,
) -> None:
    namespace = DatabaseNamespace(event_runtime.database)
    events = DatabaseEventStream(event_runtime.database)
    node = await namespace.create_node(ROOT_ID, "private-filename", NodeKind.FILE, metadata())
    created = await events.list_after(0, 100)
    assert len(created) == 2
    assert all(event.event.event_type == FILESYSTEM_DISCOVERY_CHANGED for event in created)
    assert all(event.event.subject == "filesystem" and event.event.metadata == {} for event in created)
    updated = await namespace.update_node(
        node.id, content=ContentRef(key="private-key", size=3), expected_revision=node.revision,
    )
    assert await events.list_after(created[-1].sequence, 100) == []
    await namespace.delete_node(updated.id, expected_revision=updated.revision)
    assert len(await events.list_after(created[-1].sequence, 100)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["owner", "grant", "remove", "clear", "sharing"])
async def test_policy_mutations_emit_sanitized_events(
    event_runtime: PersistenceRuntime, mutation: str,
) -> None:
    policies = DatabaseAccessControl(event_runtime.database)
    events = DatabaseEventStream(event_runtime.database)
    grant = AccessGrant(
        node_id=ROOT_ID, principal=subject(), permissions={Permission.DISCOVER}, recursive=False,
    )
    if mutation == "owner":
        await policies.set_owner(Ownership(node_id=ROOT_ID, owner=subject()))
    elif mutation == "grant":
        await policies.add_grant(grant)
    elif mutation == "remove":
        await policies.remove_grant(ROOT_ID, subject())
    elif mutation == "clear":
        await policies.clear_node(ROOT_ID)
    else:
        async with DatabaseSharingTransactions(event_runtime.database).transaction() as session:
            await session.grants.upsert(grant)
    observed = await events.list_after(0, 100)
    assert len(observed) == 1
    assert observed[0].event.event_type == FILESYSTEM_DISCOVERY_CHANGED
    assert observed[0].event.subject == "filesystem"
    assert observed[0].event.metadata == {}


@pytest.mark.asyncio
async def test_namespace_policy_and_events_rollback_together(
    event_runtime: PersistenceRuntime,
) -> None:
    with pytest.raises(ValueError, match="abort"):
        async with event_runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            namespace = SessionNamespace(session)
            await namespace.initialize_root()
            node = await namespace.create_node(ROOT_ID, "rollback-file", NodeKind.FILE, metadata())
            await SessionAccessControl(session).set_owner(Ownership(node_id=node.id, owner=subject()))
            raise ValueError("abort")
    snapshot = await DatabaseFilesystemAuthorizationReader(event_runtime.database).read()
    assert snapshot.nodes == ()
    assert snapshot.ownerships == ()
    assert await DatabaseEventStream(event_runtime.database).list_after(0, 100) == []


class ConcurrentPolicyChangeDatabase:
    def __init__(self, database: Database) -> None:
        self.database = database

    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[ReadSession]:
        async with self.database.read_session() as read_session:
            async with self.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
                await SessionAccessControl(session).clear_node(ROOT_ID)
            yield read_session


@pytest.mark.asyncio
async def test_reader_observes_committed_nodes_owners_and_grants_without_writer_reservation(
    event_runtime: PersistenceRuntime,
) -> None:
    async with event_runtime.database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
        await SessionNamespace(session).initialize_root()
        await SessionAccessControl(session).set_owner(Ownership(node_id=ROOT_ID, owner=subject()))
        await SessionAccessControl(session).add_grant(AccessGrant(
            node_id=ROOT_ID, principal=subject(), permissions={Permission.DISCOVER}, recursive=True,
        ))
    reader = DatabaseFilesystemAuthorizationReader(ConcurrentPolicyChangeDatabase(event_runtime.database))
    snapshot = await reader.read()
    assert len(snapshot.nodes) == len(snapshot.ownerships) == len(snapshot.grants) == 1
    assert snapshot.ownerships[0].owner == subject()
    assert snapshot.grants[0].permissions == frozenset({Permission.DISCOVER})
