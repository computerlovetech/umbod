from umbod.core.callers import CallerContext

from ..errors import MissingNode, OwnershipNotFound
from ..models import NodeId, Permission
from ..ports import AccessControlDriver, NamespaceDriver
from .errors import PermissionDenied
from .models import AuthorizationDecision, UnresolvedIdentity
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
        self, caller: CallerContext, node_id: NodeId, permission: Permission
    ) -> AuthorizationDecision:
        allowed = await self._allows(caller, node_id, permission)
        return AuthorizationDecision(
            node_id=node_id, permission=permission, allowed=allowed
        )

    async def _allows(
        self, caller: CallerContext, node_id: NodeId, permission: Permission
    ) -> bool:
        identity = await self._resolver.resolve(caller)
        if isinstance(identity, UnresolvedIdentity):
            return False
        try:
            await self._namespace.get_node(node_id)
            ownership = await self._access_control.get_owner(node_id)
        except (MissingNode, OwnershipNotFound):
            return False
        principals = identity.principals
        if ownership.owner in principals:
            return True
        grants = await self._access_control.list_grants(node_id)
        return any(
            grant.node_id == node_id
            and grant.principal in principals
            and permission in grant.permissions
            for grant in grants
        )

    async def require(
        self, caller: CallerContext, node_id: NodeId, permission: Permission
    ) -> None:
        decision = await self.decide(caller, node_id, permission)
        if not decision.allowed:
            raise PermissionDenied(f"{permission.value} denied for node {node_id}")
