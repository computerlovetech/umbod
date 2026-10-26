from contextlib import AbstractAsyncContextManager
from typing import Protocol

from ..models import AccessGrant, Principal
from .models import RootGroupPolicyView, RootPolicyState, SaveRootGroupPolicy


class RootGroupPolicyManagement(Protocol):
    async def inspect(self) -> RootGroupPolicyView: ...

    async def save(self, command: SaveRootGroupPolicy) -> RootGroupPolicyView: ...


class RootPolicySession(Protocol):
    async def observe(self) -> RootPolicyState: ...

    async def ensure_root(self) -> None: ...

    async def remove_group(self, principal: Principal) -> None: ...

    async def add_group(self, grant: AccessGrant) -> None: ...


class RootPolicyTransactions(Protocol):
    def read(self) -> AbstractAsyncContextManager[RootPolicySession]: ...

    def write(self) -> AbstractAsyncContextManager[RootPolicySession]: ...
