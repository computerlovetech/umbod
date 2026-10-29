from umbod.core.callers import CallerSnapshot

from ..authorization import (
    FilesystemIdentityResolver, PermissionDenied, ResolvedIdentity, UnresolvedIdentity,
    allows_resolved,
)
from ..errors import WrongNodeKind
from ..models import NodeId, NodeKind, Permission
from ..transactions import FilesystemSession, FilesystemTransactions


class DeletionService:
    def __init__(
        self, resolver: FilesystemIdentityResolver, transactions: FilesystemTransactions,
    ) -> None:
        self._resolver = resolver
        self._transactions = transactions

    async def _identity(self, snapshot: CallerSnapshot) -> ResolvedIdentity:
        identity = await self._resolver.resolve(snapshot)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied()
        return identity

    async def _require_file(
        self, session: FilesystemSession, identity: ResolvedIdentity, node_id: NodeId,
    ) -> None:
        for permission in (Permission.DISCOVER, Permission.DELETE):
            if not await allows_resolved(
                identity, node_id, permission, session.namespace, session.access_control,
            ):
                raise PermissionDenied()
        node = await session.namespace.get_node(node_id)
        if node.kind != NodeKind.FILE:
            raise WrongNodeKind(str(node_id))

    async def check_delete_eligibility(self, snapshot: CallerSnapshot, node_id: NodeId) -> None:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            await self._require_file(session, identity, node_id)

    async def delete_file(
        self, snapshot: CallerSnapshot, node_id: NodeId, *, expected_revision: int,
    ) -> None:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            await self._require_file(session, identity, node_id)
            await session.namespace.delete_node(node_id, expected_revision=expected_revision)
            await session.access_control.clear_node(node_id)
