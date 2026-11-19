from collections.abc import Sequence

from umbod.core.callers import CallerSnapshot

from ..authorization import FilesystemIdentityResolver, PermissionDenied, ResolvedIdentity, UnresolvedIdentity
from ..authorization.service import allows_resolved, resolved_access
from ..browsing import NodeSummary
from ..browsing.service import summary
from ..errors import MissingNode, OwnershipNotFound
from ..models import Node, NodeId, NodeKind, Permission, RootParent
from ..namespaces.models import NamespacePolicy
from ..transactions import FilesystemReadSession, FilesystemSession, FilesystemTransactions
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
        visibility = _namespace_visibility(policy)
    return _project_access(node, current.kind, visibility, permissions)


def _namespace_visibility(policy: NamespacePolicy) -> NamespaceVisibility:
    return NamespaceVisibility(type="namespace", namespace_id=policy.id, kind=policy.kind, name=policy.name)


def _project_access(
    node: NodeSummary, kind: NodeKind, visibility: Visibility, permissions: frozenset[Permission],
) -> CallerNodeSummary:
    return CallerNodeSummary(
        **node.model_dump(exclude={"permissions", "visible_to"}),
        permissions=CallerPermissions(
            can_discover=Permission.DISCOVER in permissions,
            can_read=Permission.READ in permissions,
            can_write=Permission.WRITE in permissions,
            can_share=Permission.SHARE in permissions,
            can_delete=kind == NodeKind.FILE and Permission.DELETE in permissions,
        ),
        visible_to=visibility,
    )


async def _is_user_owned(session: FilesystemReadSession, identity: ResolvedIdentity, node_id: NodeId) -> bool:
    try:
        ownership = await session.access_control.get_owner(node_id)
    except OwnershipNotFound:
        return False
    return ownership.owner == identity.user


async def _shared_summary(session: FilesystemReadSession, identity: ResolvedIdentity, node: Node) -> NodeSummary:
    parent_id = node.parent_id
    if isinstance(parent_id, RootParent) or await allows_resolved(
        identity, parent_id, Permission.DISCOVER, session.namespace, session.access_control,
    ):
        return summary(node)
    return summary(node).model_copy(update={"parent_id": RootParent()})


class AccessMetadataService:
    def __init__(self, resolver: FilesystemIdentityResolver, transactions: FilesystemTransactions) -> None:
        self._resolver = resolver
        self._transactions = transactions

    async def list_shared_with_me(self, caller: CallerSnapshot) -> list[CallerNodeSummary]:
        identity = await self._resolver.resolve(caller)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied()
        async with self._transactions.read() as session:
            candidates = await session.access_control.list_granted_node_ids(identity.principals)
            nodes: list[CallerNodeSummary] = []
            for node_id in sorted(candidates):
                policy, permissions = await resolved_access(identity, node_id, session.namespace, session.access_control)
                if policy is None or node_id == policy.root_node_id or Permission.DISCOVER not in permissions:
                    continue
                if await _is_user_owned(session, identity, node_id):
                    continue
                node = await session.namespace.get_node(node_id)
                visibility: Visibility = RestrictedVisibility(type="restricted")
                if Permission.DISCOVER in policy.permissions(identity.principals):
                    visibility = _namespace_visibility(policy)
                node_summary = await _shared_summary(session, identity, node)
                nodes.append(_project_access(node_summary, node.kind, visibility, permissions))
            return nodes

    async def enrich_nodes(
        self, caller: CallerSnapshot, nodes: Sequence[NodeSummary],
    ) -> list[CallerNodeSummary]:
        nodes = tuple(NodeSummary.model_validate(node) for node in nodes)
        identity = await self._resolver.resolve(caller)
        if isinstance(identity, UnresolvedIdentity):
            raise PermissionDenied()
        async with self._transactions.transaction() as session:
            return [await project_node_access(session, identity, node) for node in nodes]
