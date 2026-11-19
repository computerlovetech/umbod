from umbod.core.callers import CallerSnapshot

from ..errors import MissingNode, OwnershipNotFound, PolicyDecodingFailure
from ..models import AccessGrant, NodeId, Ownership, Permission, RootParent
from ..ports import AccessControlReader, NodeReader
from ..namespaces.models import NamespacePolicy
from .discovery import AuthorizationNode, EffectivePermissionEvaluator
from .errors import PermissionDenied
from .models import AuthorizationDecision, ResolvedIdentity, UnresolvedIdentity
from .ports import FilesystemIdentityResolver


class AuthorizationService:
    def __init__(
        self,
        resolver: FilesystemIdentityResolver,
        namespace: NodeReader,
        access_control: AccessControlReader,
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
    namespace: NodeReader,
    access_control: AccessControlReader,
) -> bool:
    return permission in await resolved_permissions(identity, node_id, namespace, access_control)


async def resolved_permissions(
    identity: ResolvedIdentity,
    node_id: NodeId,
    namespace: NodeReader,
    access_control: AccessControlReader,
) -> frozenset[Permission]:
    _, permissions = await resolved_access(identity, node_id, namespace, access_control)
    return permissions


async def resolved_access(
    identity: ResolvedIdentity, node_id: NodeId, namespace: NodeReader,
    access_control: AccessControlReader,
) -> tuple[NamespacePolicy | None, frozenset[Permission]]:
    nodes: list[AuthorizationNode] = []
    visited: set[NodeId] = set()
    current_id = node_id
    try:
        policies = await access_control.list_namespace_policies()
        while current_id not in visited:
            visited.add(current_id)
            node = await namespace.get_node(current_id)
            if node.id != current_id:
                return None, frozenset()
            nodes.append(AuthorizationNode(node_id=node.id, kind=node.kind, parent_id=node.parent_id))
            if isinstance(node.parent_id, RootParent):
                break
            current_id = node.parent_id
        evaluator = EffectivePermissionEvaluator(identity.principals, nodes, (), (), policies)
        policy = evaluator.namespace(node_id)
        if policy is None:
            return None, frozenset()
        if policy.root_node_id == node_id:
            return policy, policy.permissions(identity.principals)
        if policy.kind == "personal" and policy.owners.intersection(identity.principals):
            return policy, frozenset(Permission)
        owners: list[Ownership] = []
        try:
            owners.append(await access_control.get_owner(node_id))
        except OwnershipNotFound:
            pass
        if any(owner.node_id == node_id and owner.owner in identity.principals for owner in owners):
            return policy, frozenset(Permission)
        grants: list[AccessGrant] = []
        for node in nodes:
            if node.node_id == policy.root_node_id:
                break
            grants.extend(await access_control.list_grants(node.node_id))
        evaluator = EffectivePermissionEvaluator(identity.principals, nodes, owners, grants, policies)
        return policy, evaluator.permissions(node_id)
    except (MissingNode, PolicyDecodingFailure):
        return None, frozenset()
