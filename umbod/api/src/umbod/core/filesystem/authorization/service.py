from umbod.core.callers import CallerSnapshot

from ..errors import MissingNode, OwnershipNotFound, PolicyDecodingFailure
from ..models import NodeId, Permission, RootParent
from ..ports import AccessControlDriver, NamespaceDriver
from .discovery import AuthorizationNode, effective_permissions
from .errors import PermissionDenied
from .models import AuthorizationDecision, ResolvedIdentity, UnresolvedIdentity
from .ports import FilesystemIdentityResolver


class AuthorizationService:
    def __init__(
        self,
        resolver: FilesystemIdentityResolver,
        namespace: NamespaceDriver,
        access_control: AccessControlDriver,
    ) -> None:
        self._resolver = resolver
        self._namespace = namespace
        self._access_control = access_control

    async def decide(
        self, caller: CallerSnapshot, node_id: NodeId, permission: Permission
    ) -> AuthorizationDecision:
        allowed = await self._allows(caller, node_id, permission)
        return AuthorizationDecision(
            node_id=node_id, permission=permission, allowed=allowed
        )

    async def _allows(
        self, caller: CallerSnapshot, node_id: NodeId, permission: Permission
    ) -> bool:
        identity = await self._resolver.resolve(caller)
        if isinstance(identity, UnresolvedIdentity):
            return False
        return await allows_resolved(identity, node_id, permission, self._namespace, self._access_control)

    async def require(
        self, caller: CallerSnapshot, node_id: NodeId, permission: Permission
    ) -> None:
        decision = await self.decide(caller, node_id, permission)
        if not decision.allowed:
            raise PermissionDenied(f"{permission.value} denied for node {node_id}")


async def allows_resolved(
    identity: ResolvedIdentity,
    node_id: NodeId,
    permission: Permission,
    namespace: NamespaceDriver,
    access_control: AccessControlDriver,
) -> bool:
    return permission in await resolved_permissions(identity, node_id, namespace, access_control)


async def resolved_permissions(
    identity: ResolvedIdentity,
    node_id: NodeId,
    namespace: NamespaceDriver,
    access_control: AccessControlDriver,
) -> frozenset[Permission]:
    nodes: list[AuthorizationNode] = []
    visited: set[NodeId] = set()
    current_id = node_id
    try:
        ownership = await access_control.get_owner(node_id)
        while current_id not in visited:
            visited.add(current_id)
            node = await namespace.get_node(current_id)
            if node.id != current_id:
                return frozenset()
            nodes.append(AuthorizationNode(node_id=node.id, kind=node.kind, parent_id=node.parent_id))
            if isinstance(node.parent_id, RootParent):
                break
            current_id = node.parent_id
        owner_permissions = effective_permissions(identity.principals, node_id, (ownership,), (), nodes)
        if owner_permissions:
            return owner_permissions
        grants = []
        for node in nodes:
            grants.extend(await access_control.list_grants(node.node_id))
        return effective_permissions(identity.principals, node_id, (ownership,), grants, nodes)
    except (MissingNode, OwnershipNotFound, PolicyDecodingFailure):
        return frozenset()
