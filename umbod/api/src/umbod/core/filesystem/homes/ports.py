from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Optional, Protocol

from ..models import Principal
from ..transactions import FilesystemSession
from .models import HomeBinding


class HomeStore(Protocol):
    async def get(self, user: Principal) -> Optional[HomeBinding]: ...
    async def save(self, binding: HomeBinding) -> None: ...


@dataclass(frozen=True)
class HomeTransaction(FilesystemSession):
    homes: HomeStore


class HomeTransactions(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[HomeTransaction]: ...
