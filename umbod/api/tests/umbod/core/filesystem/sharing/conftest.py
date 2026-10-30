from dataclasses import dataclass

import pytest_asyncio

from umbod.core.filesystem import (
    AccessControlDriver, NamespaceDriver, Node, NodeKind, Ownership,
)
from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.filesystem.sharing import FilesystemSharing
from umbod.core.groups import GroupManagementService
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.persistence import Database, PersistenceRuntime
from umbod.infrastructure import (
    create_access_control_driver, create_filesystem_sharing, create_namespace_driver,
)
from tests.umbod.core.filesystem.test_authorized_content import alice, metadata


@dataclass(frozen=True)
class SharingContext:
    service: FilesystemSharing
    namespace: NamespaceDriver
    policies: AccessControlDriver
    groups: GroupManagementService
    database: Database
    node: Node


async def sharing_context(database: Database) -> SharingContext:
    namespace = create_namespace_driver(database=database)
    node = await namespace.create_node((await namespace.get_root()).id, "shared", NodeKind.DIRECTORY, metadata())
    policies = create_access_control_driver(database=database)
    await policies.set_owner(Ownership(node_id=node.id, owner=alice()))
    return SharingContext(
        service=create_filesystem_sharing(database=database, resolver=VerifiedIdentityResolver(), issuer="issuer"),
        namespace=namespace, policies=policies,
        groups=create_group_management(database), database=database, node=node,
    )


@pytest_asyncio.fixture
async def context(filesystem_runtime: PersistenceRuntime) -> SharingContext:
    return await sharing_context(filesystem_runtime.database)
