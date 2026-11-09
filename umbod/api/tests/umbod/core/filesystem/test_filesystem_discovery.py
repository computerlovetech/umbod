from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError

from umbod.core.filesystem.authorization import (
    AuthorizationGrant,
    AuthorizationNode,
    FilesystemAuthorizationReader,
    FilesystemAuthorizationSnapshot,
    FilesystemOperation,
    ResolvedIdentity,
    allows_resolved,
    permitted_operations,
)
from umbod.core.filesystem.models import (
    AccessGrant, NodeKind, Ownership, Permission, Principal, PrincipalType, RootParent,
)
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.stores import DatabaseFilesystemAuthorizationReader
from umbod.core.persistence import Database, PersistenceRuntime, ReadSession
from tests.persistence_runtime import prepared_inmemory_runtime


@pytest_asyncio.fixture
async def discovery_runtime() -> AsyncIterator[PersistenceRuntime]:
    runtime = await prepared_inmemory_runtime()
    try:
        yield runtime
    finally:
        await runtime.shutdown()


def principal(identifier: str) -> Principal:
    return Principal(type=PrincipalType.USER, issuer="issuer", id=identifier)


def identity() -> ResolvedIdentity:
    return ResolvedIdentity(user=principal("reader"), groups=frozenset())


def snapshot(
    node_id: UUID, kind: NodeKind, permissions: frozenset[Permission]
) -> FilesystemAuthorizationSnapshot:
    return FilesystemAuthorizationSnapshot(
        nodes=(AuthorizationNode(node_id=ROOT_ID, kind=NodeKind.DIRECTORY, parent_id=RootParent()),) + (
            (AuthorizationNode(node_id=node_id, kind=kind, parent_id=ROOT_ID),) if node_id != ROOT_ID else ()
        ),
        ownerships=(Ownership(node_id=node_id, owner=principal("owner")),),
        grants=(AuthorizationGrant(
            node_id=node_id, principal=identity().user,
            permissions=permissions, recursive=True,
        ),),
    )


@pytest.mark.parametrize(
    "kind,permissions,expected",
    [
        (NodeKind.FILE, frozenset(), frozenset()),
        (NodeKind.FILE, frozenset({Permission.READ}), frozenset()),
        (NodeKind.FILE, frozenset({Permission.DISCOVER}), frozenset({FilesystemOperation.INSPECT})),
        (NodeKind.FILE, frozenset(Permission), frozenset({FilesystemOperation.HOME, FilesystemOperation.INSPECT, FilesystemOperation.READ, FilesystemOperation.DELETE, FilesystemOperation.SHARE, FilesystemOperation.UPDATE_METADATA})),
        (NodeKind.DIRECTORY, frozenset(Permission), frozenset({FilesystemOperation.INSPECT, FilesystemOperation.LIST, FilesystemOperation.CREATE, FilesystemOperation.SHARE, FilesystemOperation.UPDATE_METADATA})),
    ],
)
def test_operations_require_discovery_and_matching_kind(
    kind: NodeKind, permissions: frozenset[Permission], expected: frozenset[FilesystemOperation]
) -> None:
    assert permitted_operations(snapshot(uuid4(), kind, permissions), identity()) == expected | {FilesystemOperation.HOME}


def test_only_canonical_root_authorizes_inspect_root() -> None:
    projection = snapshot(ROOT_ID, NodeKind.DIRECTORY, frozenset({Permission.DISCOVER}))
    assert FilesystemOperation.INSPECT_ROOT in permitted_operations(projection, identity())


@pytest.mark.parametrize("absent", ["nodes", "ownerships"])
def test_missing_nodes_and_unowned_nodes_are_denied(absent: str) -> None:
    projection = snapshot(uuid4(), NodeKind.FILE, frozenset(Permission))
    values = projection.model_dump()
    values[absent] = ()
    assert permitted_operations(FilesystemAuthorizationSnapshot.model_validate(values), identity()) == {FilesystemOperation.HOME}


def test_owner_has_all_permissions_without_grants() -> None:
    node_id = uuid4()
    projection = FilesystemAuthorizationSnapshot(
        nodes=snapshot(node_id, NodeKind.FILE, frozenset()).nodes,
        ownerships=(Ownership(node_id=node_id, owner=identity().user),),
        grants=(),
    )
    assert permitted_operations(projection, identity()) == frozenset({
        FilesystemOperation.HOME, FilesystemOperation.INSPECT, FilesystemOperation.READ,
        FilesystemOperation.DELETE, FilesystemOperation.SHARE, FilesystemOperation.UPDATE_METADATA,
    })


def test_grants_union_across_matching_principals_on_same_node() -> None:
    group = Principal(type=PrincipalType.GROUP, issuer="issuer", id="team")
    caller = ResolvedIdentity(user=identity().user, groups=frozenset({group}))
    node_id = uuid4()
    projection = snapshot(node_id, NodeKind.FILE, frozenset({Permission.DISCOVER}))
    projection = FilesystemAuthorizationSnapshot(
        nodes=projection.nodes, ownerships=projection.ownerships,
        grants=projection.grants + (AuthorizationGrant(
            node_id=node_id, principal=group,
            permissions=frozenset({Permission.READ}), recursive=False,
        ),),
    )
    assert FilesystemOperation.READ in permitted_operations(projection, caller)


@pytest.mark.parametrize("component", ["node", "issuer", "type", "id"])
def test_unrelated_grants_cannot_supply_required_permission(component: str) -> None:
    node_id = uuid4()
    grant_id = uuid4() if component == "node" else node_id
    subject = Principal(
        type=PrincipalType.GROUP if component == "type" else PrincipalType.USER,
        issuer="foreign" if component == "issuer" else "issuer",
        id="foreign" if component == "id" else "reader",
    )
    projection = snapshot(node_id, NodeKind.FILE, frozenset({Permission.DISCOVER}))
    projection = FilesystemAuthorizationSnapshot(
        nodes=projection.nodes, ownerships=projection.ownerships,
        grants=projection.grants + (AuthorizationGrant(
            node_id=grant_id, principal=subject,
            permissions=frozenset({Permission.READ}), recursive=True,
        ),),
    )
    assert permitted_operations(projection, identity()) == frozenset({FilesystemOperation.HOME, FilesystemOperation.INSPECT})


def test_snapshot_is_deeply_immutable_and_rejects_duplicate_nodes() -> None:
    projection = snapshot(uuid4(), NodeKind.FILE, frozenset({Permission.DISCOVER}))
    with pytest.raises(ValidationError):
        projection.nodes = ()
    assert isinstance(projection.grants[0].permissions, frozenset)
    with pytest.raises(ValidationError):
        FilesystemAuthorizationSnapshot(
            nodes=projection.nodes + projection.nodes,
            ownerships=projection.ownerships, grants=projection.grants,
        )


class ObservedReadDatabase:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.sessions = 0

    @asynccontextmanager
    async def read_session(self) -> AsyncIterator[ReadSession]:
        self.sessions += 1
        async with self.database.read_session() as session:
            yield session


@pytest.mark.asyncio
async def test_reader_uses_one_read_only_session_without_initializing_root(
    discovery_runtime: PersistenceRuntime,
) -> None:
    database = ObservedReadDatabase(discovery_runtime.database)
    reader: FilesystemAuthorizationReader = DatabaseFilesystemAuthorizationReader(database)
    projection = await reader.read()
    assert projection == FilesystemAuthorizationSnapshot(nodes=(), ownerships=(), grants=())
    assert database.sessions == 1


class InMemoryAuthorizationReader:
    def __init__(self, projection: FilesystemAuthorizationSnapshot) -> None:
        self.projection = projection

    async def read(self) -> FilesystemAuthorizationSnapshot:
        return self.projection


@pytest.mark.asyncio
async def test_reader_port_accepts_inmemory_snapshot() -> None:
    projection = snapshot(uuid4(), NodeKind.FILE, frozenset(Permission))
    reader: FilesystemAuthorizationReader = InMemoryAuthorizationReader(projection)
    assert await reader.read() == projection


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions", [frozenset(), frozenset(Permission)])
async def test_execution_and_projection_share_permission_evaluation(
    discovery_runtime: PersistenceRuntime, permissions: frozenset[Permission],
) -> None:
    from umbod.core.filesystem.models import NodeMetadata, UnspecifiedContentType
    from umbod.core.filesystem.stores import DatabaseAccessControl, DatabaseNamespace

    namespace = DatabaseNamespace(discovery_runtime.database)
    policies = DatabaseAccessControl(discovery_runtime.database)
    node = await namespace.create_node(
        ROOT_ID, "file", NodeKind.FILE,
        NodeMetadata(content_type=UnspecifiedContentType(), attributes={}),
    )
    await policies.set_owner(Ownership(node_id=node.id, owner=principal("owner")))
    await policies.add_grant(AccessGrant(
        node_id=node.id, principal=identity().user,
        permissions=set(permissions), recursive=True,
    ))
    projection = await DatabaseFilesystemAuthorizationReader(discovery_runtime.database).read()
    assert await allows_resolved(identity(), node.id, Permission.READ, namespace, policies) == (
        FilesystemOperation.READ in permitted_operations(projection, identity())
    )
