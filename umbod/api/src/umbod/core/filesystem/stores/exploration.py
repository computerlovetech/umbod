from umbod.core.persistence import (
    AllFields, Database, Equals, OneOf, Query, ReadPlan, ReadSession, Unordered,
)

from ..authorization import PermissionDenied, ResolvedIdentity
from ..authorization.discovery import AuthorizationNode, effective_permissions
from ..browsing.exploration.models import BrowseScope
from ..browsing.service import discover_denied
from ..errors import StorageFailure
from ..models import AccessGrant, Node, NodeId, NodeKind, Ownership, Permission, RootParent
from .schema import NODE_ID, NODE_PARENT, NODE_TABLE, OWNER_NODE, OWNER_TABLE, GRANT_NODE, GRANT_TABLE


async def scoped_policies(
    session: ReadSession, node_ids: tuple[NodeId, ...],
) -> tuple[tuple[Ownership, ...], tuple[AccessGrant, ...]]:
    plan = ReadPlan()
    ids = sorted({str(value) for value in node_ids})
    owner_reads = []
    grant_reads = []
    for offset in range(0, len(ids), 200):
        batch = tuple(ids[offset:offset + 200])
        owner_reads.append(plan.find_many(
            OWNER_TABLE, Query(filter=OneOf(OWNER_NODE, batch),
                               projection=AllFields(), ordering=Unordered()),
        ))
        grant_reads.append(plan.find_many(
            GRANT_TABLE, Query(filter=OneOf(GRANT_NODE, batch),
                               projection=AllFields(), ordering=Unordered()),
        ))
    results = await plan.execute(session)
    return (
        tuple(row.payload for read in owner_reads for row in results.get(read)),
        tuple(row.payload for read in grant_reads for row in results.get(read)),
    )


class DatabaseBrowseScopeReader:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def read_scope(self, node_id: NodeId, identity: ResolvedIdentity) -> BrowseScope:
        try:
            async with self._database.read_session() as session:
                record = await session.find_one(
                    NODE_TABLE, Query(filter=Equals(NODE_ID, str(node_id)),
                                      projection=AllFields(), ordering=Unordered()),
                )
                if record is None:
                    raise discover_denied(node_id)
                target = record.payload
                nodes: dict[NodeId, Node] = {target.id: target}
                current = target
                while not isinstance(current.parent_id, RootParent) and current.parent_id not in nodes:
                    record = await session.find_one(
                        NODE_TABLE, Query(filter=Equals(NODE_ID, str(current.parent_id)),
                                          projection=AllFields(), ordering=Unordered()),
                    )
                    if record is None:
                        break
                    current = record.payload
                    nodes[current.id] = current
                policy_ids = set(nodes)
                ownerships, grants = await scoped_policies(session, tuple(nodes))
                ancestry = tuple(
                    AuthorizationNode(node_id=node.id, kind=node.kind, parent_id=node.parent_id)
                    for node in nodes.values()
                )
                if Permission.DISCOVER not in effective_permissions(
                    identity.principals, node_id, ownerships, grants, ancestry,
                ):
                    raise discover_denied(node_id)
                if target.kind == NodeKind.DIRECTORY:
                    children = await session.find_many(
                        NODE_TABLE, Query(filter=Equals(NODE_PARENT, str(node_id)),
                                          projection=AllFields(), ordering=Unordered()),
                    )
                    nodes.update((record.payload.id, record.payload) for record in children)
                related_owners, related_grants = await scoped_policies(
                    session, tuple(value for value in nodes if value not in policy_ids),
                )
                return BrowseScope(
                    nodes=tuple(nodes.values()), ownerships=ownerships + related_owners,
                    grants=grants + related_grants,
                )
        except PermissionDenied:
            raise
        except Exception as error:
            raise StorageFailure("Filesystem exploration read failed") from error
