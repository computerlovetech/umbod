from uuid import uuid4

import pytest
from pydantic import ValidationError

from umbod.core.filesystem.authorization import AuthorizationNode, FilesystemAuthorizationSnapshot, FilesystemOperation, ResolvedIdentity, permitted_operations
from umbod.core.filesystem.models import NodeKind, Principal, PrincipalType, RootParent
from umbod.core.filesystem.namespace import ROOT_ID
from umbod.core.filesystem.stores import DatabaseFilesystemAuthorizationReader
from umbod.core.persistence import PersistenceRuntime
from tests.umbod.core.filesystem.test_effective_permissions import policy


@pytest.mark.parametrize("kind", list(NodeKind))
def test_managed_namespace_operations_exclude_root_inspection_and_sharing(kind: NodeKind) -> None:
    root_id, target_id = uuid4(), uuid4()
    namespace = policy(root_id)
    nodes = (
        AuthorizationNode(node_id=ROOT_ID, kind=NodeKind.DIRECTORY, parent_id=RootParent()),
        AuthorizationNode(node_id=root_id, kind=NodeKind.DIRECTORY, parent_id=ROOT_ID),
        AuthorizationNode(node_id=target_id, kind=kind, parent_id=root_id),
    )
    identity = ResolvedIdentity(user=Principal(type=PrincipalType.USER, issuer="issuer", id="alice"), groups=frozenset())
    snapshot = FilesystemAuthorizationSnapshot(nodes=nodes, ownerships=(), grants=(), namespaces=(namespace,))
    expected = {FilesystemOperation.HOME, FilesystemOperation.INSPECT, FilesystemOperation.LIST, FilesystemOperation.CREATE, FilesystemOperation.UPDATE_METADATA}
    if kind == NodeKind.FILE:
        expected.update({FilesystemOperation.READ, FilesystemOperation.DELETE})
    expected.add(FilesystemOperation.SHARE)
    assert permitted_operations(snapshot, identity) == expected
    assert permitted_operations(snapshot.model_copy(update={"namespaces": ()}), identity) == {FilesystemOperation.HOME}
    with pytest.raises(ValidationError):
        snapshot.nodes = ()
    with pytest.raises(ValidationError):
        FilesystemAuthorizationSnapshot(nodes=nodes + nodes, ownerships=(), grants=(), namespaces=(namespace,))


@pytest.mark.asyncio
async def test_empty_reader_does_not_initialize_structural_root(filesystem_runtime: PersistenceRuntime) -> None:
    snapshot = await DatabaseFilesystemAuthorizationReader(filesystem_runtime.database).read()
    assert snapshot == FilesystemAuthorizationSnapshot(nodes=(), ownerships=(), grants=(), namespaces=())
