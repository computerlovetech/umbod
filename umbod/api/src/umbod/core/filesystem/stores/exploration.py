from umbod.core.persistence import (
    AllFields, Database, Equals, Query, Unordered,
)

from ..authorization import PermissionDenied, ResolvedIdentity
from ..authorization.discovery import AuthorizationGrant, AuthorizationNode, EffectivePermissionEvaluator
from ..browsing.exploration.models import BrowseScope
from ..browsing.service import discover_denied
from ..errors import StorageFailure
from ..models import Node, NodeId, NodeKind, Ownership, Permission, RootParent
from .namespaces import namespace_policies
from .schema import NODE_ID, NODE_PARENT, NODE_TABLE
from .authorization_facts import read_scoped_acls


class DatabaseBrowseScopeReader:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def read_scope(self, node_id: NodeId, identity: ResolvedIdentity) -> BrowseScope:
        try:
            async with self._database.read_session() as session:
                record = await session.find_one(
                    NODE_TABLE, Query(filter=Equals(NODE_ID, str(node_id)), projection=AllFields(), ordering=Unordered()),
                )
                if record is None:
                    raise discover_denied(node_id)
                target = record.payload
                nodes: dict[NodeId, Node] = {target.id: target}
                current = target
                while not isinstance(current.parent_id, RootParent) and current.parent_id not in nodes:
                    record = await session.find_one(
                        NODE_TABLE, Query(filter=Equals(NODE_ID, str(current.parent_id)), projection=AllFields(), ordering=Unordered()),
                    )
                    if record is None:
                        break
                    current = record.payload
                    nodes[current.id] = current
                policies = tuple(await namespace_policies(session))
                ancestry = tuple(
                    AuthorizationNode(node_id=node.id, kind=node.kind, parent_id=node.parent_id)
                    for node in nodes.values()
                )
                evaluator = EffectivePermissionEvaluator(identity.principals, ancestry, (), (), policies)
                policy = evaluator.namespace(node_id)
                if policy is None:
                    raise discover_denied(node_id)
                scoped_ids: list[NodeId] = []
                for node in nodes.values():
                    if node.id == policy.root_node_id:
                        break
                    scoped_ids.append(node.id)
                ownerships, grants = await read_scoped_acls(session, tuple(scoped_ids))
                evaluator = EffectivePermissionEvaluator(identity.principals, ancestry, ownerships, grants, policies)
                if Permission.DISCOVER not in evaluator.permissions(node_id):
                    raise discover_denied(node_id)
                related_owners: tuple[Ownership, ...] = ()
                related_grants: tuple[AuthorizationGrant, ...] = ()
                if target.kind == NodeKind.DIRECTORY:
                    children = await session.find_many(
                        NODE_TABLE, Query(filter=Equals(NODE_PARENT, str(node_id)), projection=AllFields(), ordering=Unordered()),
                    )
                    namespace_roots = {policy.root_node_id for policy in policies}
                    related_owners, related_grants = await read_scoped_acls(
                        session, tuple(record.payload.id for record in children if record.payload.id not in nodes and record.payload.id not in namespace_roots),
                    )
                    nodes.update((record.payload.id, record.payload) for record in children)
                return BrowseScope(
                    nodes=tuple(nodes.values()), ownerships=ownerships + related_owners,
                    grants=grants + related_grants, namespaces=policies,
                )
        except PermissionDenied:
            raise
        except Exception as error:
            raise StorageFailure("Filesystem exploration read failed") from error
