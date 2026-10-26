from typing import Protocol, Union

from umbod.core.callers import CallerContext

from ..models import NodeId, Permission
from .models import AuthorizationDecision, ResolvedIdentity, UnresolvedIdentity


class FilesystemIdentityResolver(Protocol):
    async def resolve(
        self, caller: CallerContext
    ) -> Union[ResolvedIdentity, UnresolvedIdentity]: ...


class FilesystemAuthorization(Protocol):
    async def decide(
        self, caller: CallerContext, node_id: NodeId, permission: Permission
    ) -> AuthorizationDecision: ...

    async def require(
        self, caller: CallerContext, node_id: NodeId, permission: Permission
    ) -> None: ...
