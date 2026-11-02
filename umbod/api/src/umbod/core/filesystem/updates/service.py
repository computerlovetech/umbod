from umbod.core.callers import CallerSnapshot

from ..authorization import (
    FilesystemIdentityResolver, PermissionDenied, ResolvedIdentity, UnresolvedIdentity,
    allows_resolved,
)
from ..access import CallerNodeSummary
from ..access.service import project_node_access
from ..browsing import summary
from ..errors import RootMutation, WrongNodeKind
from ..models import Node, NodeId, NodeKind, NodeMetadata, NodeUpdate, Permission, RootParent, UnchangedContentType
from ..transactions import FilesystemSession, FilesystemTransactions
from .models import NodePatch, Unchanged


class NodeUpdateService:
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

    async def _require_write(
        self, session: FilesystemSession, identity: ResolvedIdentity, node_id: NodeId,
    ) -> None:
        for permission in (Permission.DISCOVER, Permission.WRITE):
            if not await allows_resolved(
                identity, node_id, permission, session.namespace, session.access_control,
            ):
                raise PermissionDenied()

    async def check_update_eligibility(self, snapshot: CallerSnapshot, node_id: NodeId) -> None:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            await self._require_write(session, identity, node_id)

    async def _authorize_move(
        self, session: FilesystemSession, identity: ResolvedIdentity, node: Node, destination: NodeId,
    ) -> None:
        if isinstance(node.parent_id, RootParent):
            raise RootMutation()
        await self._require_write(session, identity, node.parent_id)
        await self._require_write(session, identity, destination)
        source = await session.namespace.get_node(node.parent_id)
        target = await session.namespace.get_node(destination)
        if source.kind != NodeKind.DIRECTORY or target.kind != NodeKind.DIRECTORY:
            raise WrongNodeKind()

    def _metadata(self, node: Node, patch: NodePatch) -> NodeMetadata:
        if isinstance(patch.metadata, Unchanged):
            return node.metadata
        attributes = {**node.metadata.attributes, **patch.metadata.attributes}
        if patch.metadata.attributes.get("description") == "":
            attributes.pop("description")
        content_type = (
            node.metadata.content_type
            if isinstance(patch.metadata.content_type, UnchangedContentType) else patch.metadata.content_type
        )
        return NodeMetadata(attributes=attributes, content_type=content_type)

    async def update_node(
        self, snapshot: CallerSnapshot, node_id: NodeId, patch: NodePatch, *, expected_revision: int,
    ) -> CallerNodeSummary:
        identity = await self._identity(snapshot)
        async with self._transactions.transaction() as session:
            await self._require_write(session, identity, node_id)
            node = await session.namespace.get_node(node_id)
            if isinstance(node.parent_id, RootParent) and (
                not isinstance(patch.name, Unchanged) or not isinstance(patch.parent_id, Unchanged)
            ):
                raise RootMutation()
            if not isinstance(patch.parent_id, Unchanged):
                await self._authorize_move(session, identity, node, patch.parent_id)
            details = NodeUpdate(
                name=node.name if isinstance(patch.name, Unchanged) else patch.name,
                parent_id=node.parent_id if isinstance(patch.parent_id, Unchanged) else patch.parent_id,
                metadata=self._metadata(node, patch),
            )
            updated = await session.namespace.update_details(
                node_id, details=details, expected_revision=expected_revision,
            )
            return await project_node_access(session, identity, summary(updated))
