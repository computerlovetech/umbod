from typing import Protocol, Union

from umbod.core.callers import CallerSnapshot

from ..models import NodeId, Permission
from .discovery import FilesystemAuthorizationSnapshot
from .models import AuthorizationDecision, ResolvedIdentity, UnresolvedIdentity


class FilesystemAuthorizationReader(Protocol):
    async def read(self) -> FilesystemAuthorizationSnapshot: ...


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
