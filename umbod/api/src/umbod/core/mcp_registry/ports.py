from typing import Protocol

from .models import RegistryPage, RegistrySearch


class RegistryUnavailableError(RuntimeError):
    pass


class McpRegistry(Protocol):
    async def search(self, query: RegistrySearch) -> RegistryPage: ...
