from uuid import uuid4

from umbod.core.callers import CallerSnapshot

from ..authorization import FilesystemIdentityResolver, PermissionDenied, UnresolvedIdentity
from ..browsing import NodeSummary, summary
from ..creation.service import require_unowned_unshared_node
from ..errors import MissingNode
from ..models import NodeKind, NodeMetadata, Ownership, UnspecifiedContentType
from ..namespace import ROOT_ID
from .models import HomeBinding
from .ports import HomeTransactions


class HomeService:
    def __init__(self, resolver: FilesystemIdentityResolver, transactions: HomeTransactions) -> None:
        self._resolver = resolver
        self._transactions = transactions

    async def get_or_provision(self, caller: CallerSnapshot) -> NodeSummary:
        identity = await self._resolver.resolve(caller)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied()
        async with self._transactions.transaction() as session:
            binding = await session.homes.get(identity.user)
            if binding is not None:
                try:
                    node = await session.namespace.get_node(binding.node_id)
                except MissingNode:
                    raise PermissionDenied() from None
                if binding.user != identity.user or node.kind != NodeKind.DIRECTORY:
                    raise PermissionDenied()
                await session.homes.adopt_namespace(binding)
                return summary(node)
            node = await session.namespace.create_node(
                ROOT_ID, f"Home-{uuid4()}", NodeKind.DIRECTORY,
                NodeMetadata(content_type=UnspecifiedContentType(), attributes={}),
            )
            await require_unowned_unshared_node(session, node.id)
            await session.access_control.set_owner(Ownership(node_id=node.id, owner=identity.user))
            await session.homes.save(HomeBinding(user=identity.user, node_id=node.id))
            await session.homes.adopt_namespace(HomeBinding(user=identity.user, node_id=node.id))
            return summary(node)
