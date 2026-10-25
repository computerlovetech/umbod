import asyncio
from uuid import uuid4

import pytest

from umbod.core.filesystem import (
    AccessGrant,
    ContentRef,
    Filesystem,
    MissingNode,
    NodeKind,
    NodeMetadata,
    Ownership,
    OwnershipNotFound,
    Permission,
    Principal,
    PrincipalType,
)
from umbod.core.persistence import PersistenceRuntime
from umbod.infrastructure import (
    InMemoryContentConfig,
    create_access_control_driver,
    create_content_driver,
    create_namespace_driver,
)
from tests.support.filesystem.models import NodeHandle
from tests.support.filesystem.sharing import DirectPythonSharingDriver, SharingLanguage


@pytest.fixture
def sharing(filesystem_runtime: PersistenceRuntime) -> SharingLanguage:
    return DirectPythonSharingDriver(
        create_access_control_driver(database=filesystem_runtime.database)
    )


def subject(identifier: str) -> Principal:
    return Principal(type=PrincipalType.USER, issuer="provider", id=identifier)


@pytest.mark.asyncio
async def test_root_and_service_created_nodes_remain_unowned_until_separately_assigned(
    filesystem_runtime: PersistenceRuntime,
    sharing: SharingLanguage,
) -> None:
    namespace = create_namespace_driver(database=filesystem_runtime.database)
    filesystem = Filesystem(
        namespace=namespace,
        content=create_content_driver(InMemoryContentConfig(type="inmemory")),
    )
    root = await filesystem.get_root()
    file = await filesystem.create_file(
        root.id, "unowned", NodeMetadata(content_type="text/plain", attributes={})
    )
    for node in (root, file):
        handle = NodeHandle(str(node.id))
        with pytest.raises(OwnershipNotFound):
            await sharing.owner(handle)
        await sharing.assign_owner(handle, subject("owner"))
        assert await sharing.owner(handle) == subject("owner")
        assert await namespace.get_node(node.id) == node


@pytest.mark.asyncio
async def test_sharing_language_replaces_and_revokes_grants_without_changing_owner(
    sharing: SharingLanguage,
) -> None:
    node = NodeHandle(str(uuid4()))
    owner = subject("owner")
    reader = subject("reader")
    await sharing.assign_owner(node, owner)
    await sharing.share(node, reader, {Permission.READ, Permission.DISCOVER}, True)
    await sharing.share(node, reader, set(), False)
    grants = await sharing.grants(node)
    assert len(grants) == 1
    assert grants[0].permissions == set()
    assert grants[0].recursive is False
    await sharing.revoke(node, reader)
    await sharing.revoke(node, reader)
    assert tuple(await sharing.grants(node)) == ()
    assert await sharing.owner(node) == owner


@pytest.mark.asyncio
async def test_missing_namespace_and_missing_ownership_are_distinct(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    node_id = uuid4()
    namespace = create_namespace_driver(database=filesystem_runtime.database)
    policies = create_access_control_driver(database=filesystem_runtime.database)
    with pytest.raises(MissingNode):
        await namespace.get_node(node_id)
    with pytest.raises(OwnershipNotFound):
        await policies.get_owner(node_id)
    owner = Ownership(node_id=node_id, owner=subject("opaque-owner"))
    await policies.set_owner(owner)
    assert await policies.get_owner(node_id) == owner


@pytest.mark.asyncio
async def test_nodes_with_identical_content_reference_keep_independent_policies(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    namespace = create_namespace_driver(database=filesystem_runtime.database)
    policies = create_access_control_driver(database=filesystem_runtime.database)
    root = await namespace.get_root()
    first = await namespace.create_node(
        root.id,
        "first",
        NodeKind.FILE,
        NodeMetadata(content_type="text/plain", attributes={}),
    )
    second = await namespace.create_node(
        root.id,
        "second",
        NodeKind.FILE,
        NodeMetadata(content_type="text/plain", attributes={}),
    )
    content = ContentRef(key="a" * 32, size=4)
    for node in (first, second):
        await namespace.update_node(
            node.id, content=content, expected_revision=node.revision
        )
    owner = Ownership(node_id=first.id, owner=subject("owner"))
    await policies.set_owner(owner)
    first_grant = AccessGrant(
        node_id=first.id,
        principal=subject("reader"),
        permissions={Permission.READ},
        recursive=True,
    )
    other_grant = AccessGrant(
        node_id=first.id,
        principal=subject("writer"),
        permissions={Permission.WRITE},
        recursive=False,
    )
    second_grant = AccessGrant(
        node_id=second.id,
        principal=subject("reader"),
        permissions=set(),
        recursive=False,
    )
    for grant in (first_grant, other_grant, second_grant):
        await policies.add_grant(grant)
    await policies.remove_grant(first.id, first_grant.principal)
    assert tuple(await policies.list_grants(first.id)) == (other_grant,)
    assert tuple(await policies.list_grants(second.id)) == (second_grant,)
    assert await policies.get_owner(first.id) == owner
    with pytest.raises(OwnershipNotFound):
        await policies.get_owner(second.id)


@pytest.mark.asyncio
async def test_concurrent_owner_writes_publish_complete_owner_records(
    filesystem_runtime: PersistenceRuntime,
) -> None:
    node_id = uuid4()
    policies = create_access_control_driver(database=filesystem_runtime.database)
    owners = [
        Ownership(node_id=node_id, owner=subject(str(index))) for index in range(8)
    ]
    await asyncio.gather(
        *(
            create_access_control_driver(
                database=filesystem_runtime.database
            ).set_owner(owner)
            for owner in owners
        )
    )
    assert await policies.get_owner(node_id) in owners
    final = Ownership(node_id=node_id, owner=subject("last-applied"))
    await policies.set_owner(final)
    assert await policies.get_owner(node_id) == final
