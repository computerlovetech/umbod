from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from umbod.core.filesystem import (
    AccessControlDriver,
    AccessGrant,
    Ownership,
    Permission,
    Principal,
)

from .models import NodeHandle


class SharingLanguage(Protocol):
    async def owner(self, node: NodeHandle) -> Principal: ...
    async def assign_owner(self, node: NodeHandle, principal: Principal) -> None: ...
    async def grants(self, node: NodeHandle) -> Sequence[AccessGrant]: ...
    async def share(
        self,
        node: NodeHandle,
        principal: Principal,
        permissions: set[Permission],
        recursive: bool,
    ) -> None: ...
    async def revoke(self, node: NodeHandle, principal: Principal) -> None: ...


class DirectPythonSharingDriver:
    def __init__(self, policies: AccessControlDriver) -> None:
        self._policies = policies

    async def owner(self, node: NodeHandle) -> Principal:
        ownership = await self._policies.get_owner(UUID(node.value))
        return ownership.owner

    async def assign_owner(self, node: NodeHandle, principal: Principal) -> None:
        await self._policies.set_owner(
            Ownership(node_id=UUID(node.value), owner=principal)
        )

    async def grants(self, node: NodeHandle) -> Sequence[AccessGrant]:
        return await self._policies.list_grants(UUID(node.value))

    async def share(
        self,
        node: NodeHandle,
        principal: Principal,
        permissions: set[Permission],
        recursive: bool,
    ) -> None:
        await self._policies.add_grant(
            AccessGrant(
                node_id=UUID(node.value),
                principal=principal,
                permissions=permissions,
                recursive=recursive,
            )
        )

    async def revoke(self, node: NodeHandle, principal: Principal) -> None:
        await self._policies.remove_grant(UUID(node.value), principal)
