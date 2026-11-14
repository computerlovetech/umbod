from umbod.core.callers import CallerSnapshot
from umbod.core.filesystem.authorization import VerifiedIdentityResolver
from umbod.core.filesystem.browsing import NodeSummary, summary
from umbod.core.filesystem.models import NodeId
from umbod.core.filesystem.namespaces import CreateSharedNamespace, NamespaceGroupAccess, SaveSharedNamespace
from umbod.core.groups.models import RegisterGroup
from umbod.core.groups.stores.composition import create_group_management
from umbod.core.persistence import Database
from umbod.infrastructure import create_filesystem_homes, create_filesystem_namespace_management, create_namespace_driver


async def personal_directory(database: Database, caller: CallerSnapshot) -> NodeSummary:
    return await create_filesystem_homes(database=database, resolver=VerifiedIdentityResolver()).get_or_provision(caller)


async def shared_directory(database: Database) -> NodeSummary:
    await create_group_management(database).register_group(RegisterGroup(group_id="team"))
    view = await create_filesystem_namespace_management(database=database, issuer="issuer").create(
        CreateSharedNamespace(name="Shared", groups=[NamespaceGroupAccess(group_id="team", access="read_write")]),
    )
    return summary(await create_namespace_driver(database=database).get_node(view.root_node_id))


async def set_shared_access(database: Database, node_id: NodeId, writable: bool, discoverable: bool) -> None:
    management = create_filesystem_namespace_management(database=database, issuer="issuer")
    view = next(view for view in await management.list() if view.root_node_id == node_id)
    groups = [NamespaceGroupAccess(group_id="team", access="read_write" if writable else "read")] if discoverable else []
    await management.save(view.id, SaveSharedNamespace(name=view.name, groups=groups, expected_revision=view.revision))
