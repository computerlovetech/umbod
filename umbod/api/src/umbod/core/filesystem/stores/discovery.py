from umbod.core.persistence import AllFields, Database, NoFilter, Query, Unordered

from ..authorization.discovery import AuthorizationNode, EffectivePermissionEvaluator, FilesystemAuthorizationSnapshot
from .authorization_facts import read_scoped_acls
from .namespaces import namespace_policies
from .schema import NODE_TABLE


class DatabaseFilesystemAuthorizationReader:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def read(self) -> FilesystemAuthorizationSnapshot:
        async with self._database.read_session() as session:
            records = await session.find_many(
                NODE_TABLE,
                Query(filter=NoFilter(), projection=AllFields(), ordering=Unordered()),
            )
            nodes = tuple(
                AuthorizationNode(node_id=row.payload.id, kind=row.payload.kind, parent_id=row.payload.parent_id)
                for row in records
            )
            policies = tuple(await namespace_policies(session))
            evaluator = EffectivePermissionEvaluator(frozenset(), nodes, (), (), policies)
            managed_descendants = tuple(
                node.node_id for node in nodes
                if (policy := evaluator.namespace(node.node_id)) is not None and node.node_id != policy.root_node_id
            )
            owners, grants = await read_scoped_acls(session, managed_descendants)
            return FilesystemAuthorizationSnapshot(
                nodes=nodes, namespaces=policies, ownerships=owners, grants=grants,
            )
