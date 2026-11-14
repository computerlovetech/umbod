from collections.abc import Sequence

from umbod.core.callers import CallerSnapshot

from ..authorization import FilesystemIdentityResolver, PermissionDenied, ResolvedIdentity, UnresolvedIdentity
from ..authorization.service import resolved_access
from ..browsing import NodeSummary
from ..errors import MissingNode
from ..models import NodeKind, Permission
from ..transactions import FilesystemSession, FilesystemTransactions
from .models import CallerNodeSummary, CallerPermissions, NamespaceVisibility, RestrictedVisibility, Visibility


async def project_node_access(
    session: FilesystemSession, identity: ResolvedIdentity, node: NodeSummary,
) -> CallerNodeSummary:
    result = await project_mutation_result_access(session, identity, node)
    if not result.permissions.can_discover:
        raise PermissionDenied()
    return result


async def project_mutation_result_access(
    session: FilesystemSession, identity: ResolvedIdentity, node: NodeSummary,
) -> CallerNodeSummary:
    try:
        current = await session.namespace.get_node(node.id)
    except MissingNode:
        raise PermissionDenied() from None
    policy, permissions = await resolved_access(identity, node.id, session.namespace, session.access_control)
    visibility: Visibility = RestrictedVisibility(type="restricted")
    if policy is not None and Permission.DISCOVER in permissions:
        visibility = NamespaceVisibility(type="namespace", namespace_id=policy.id, kind=policy.kind, name=policy.name)
    return CallerNodeSummary(
        **node.model_dump(exclude={"permissions", "visible_to"}),
        permissions=CallerPermissions(
            can_discover=Permission.DISCOVER in permissions,
            can_read=Permission.READ in permissions,
            can_write=Permission.WRITE in permissions,
            can_share=Permission.SHARE in permissions,
            can_delete=current.kind == NodeKind.FILE and Permission.DELETE in permissions,
        ),
        visible_to=visibility,
    )


class AccessMetadataService:
    def __init__(self, resolver: FilesystemIdentityResolver, transactions: FilesystemTransactions) -> None:
        self._resolver = resolver
        self._transactions = transactions

    async def enrich_nodes(
        self, caller: CallerSnapshot, nodes: Sequence[NodeSummary],
    ) -> list[CallerNodeSummary]:
        nodes = tuple(NodeSummary.model_validate(node) for node in nodes)
        identity = await self._resolver.resolve(caller)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied()
        async with self._transactions.transaction() as session:
            return [await project_node_access(session, identity, node) for node in nodes]
