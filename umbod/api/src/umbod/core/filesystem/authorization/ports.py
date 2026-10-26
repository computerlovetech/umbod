from typing import Protocol, Union

from umbod.core.callers import CallerSnapshot

from ..models import NodeId, Permission
from .models import AuthorizationDecision, ResolvedIdentity, UnresolvedIdentity


class FilesystemIdentityResolver(Protocol):
    async def resolve(
        self, caller: CallerSnapshot
    ) -> Union[ResolvedIdentity, UnresolvedIdentity]: ...


class FilesystemAuthorization(Protocol):
    async def decide(
        self, caller: CallerSnapshot, node_id: NodeId, permission: Permission
    ) -> AuthorizationDecision: ...

    async def require(
        self, caller: CallerSnapshot, node_id: NodeId, permission: Permission
    ) -> None: ...
