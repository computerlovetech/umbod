from umbod.core.callers import CallerSnapshot

from ..authorization import (
    FilesystemIdentityResolver,
    PermissionDenied,
    UnresolvedIdentity,
    allows_resolved,
)
from ..browsing import NodeSummary, summary
from ..errors import OwnershipNotFound, StorageFailure
from ..models import NodeId, NodeKind, NodeMetadata, Ownership, Permission
from ..transactions import FilesystemSession, FilesystemTransactions


async def require_unowned_unshared_node(session: FilesystemSession, node_id: NodeId) -> None:
    try:
        await session.access_control.get_owner(node_id)
    except OwnershipNotFound:
        if not await session.access_control.list_grants(node_id):
            return
    raise StorageFailure("New node has pre-existing policies")


class CreationService:
    def __init__(
        self, resolver: FilesystemIdentityResolver, transactions: FilesystemTransactions
    ) -> None:
        self._resolver = resolver
        self._transactions = transactions

    async def create_file(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str, metadata: NodeMetadata
    ) -> NodeSummary:
        return await self._create(snapshot, parent_id, name, NodeKind.FILE, metadata)

    async def create_directory(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str, metadata: NodeMetadata
    ) -> NodeSummary:
        return await self._create(snapshot, parent_id, name, NodeKind.DIRECTORY, metadata)

    async def _create(
        self, snapshot: CallerSnapshot, parent_id: NodeId, name: str,
        kind: NodeKind, metadata: NodeMetadata,
    ) -> NodeSummary:
        identity = await self._resolver.resolve(snapshot)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied("Unresolved filesystem identity")
        async with self._transactions.transaction() as session:
            for permission in (Permission.DISCOVER, Permission.WRITE):
                if not await allows_resolved(
                    identity, parent_id, permission, session.namespace, session.access_control
                ):
                    raise PermissionDenied(f"{permission.value} denied for node {parent_id}")
            node = await session.namespace.create_node(parent_id, name, kind, metadata)
            await require_unowned_unshared_node(session, node.id)
            await session.access_control.set_owner(Ownership(node_id=node.id, owner=identity.user))
            result = summary(node)
        return result
