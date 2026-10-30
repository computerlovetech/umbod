from typing import Protocol

from .models import DirectoryScope, GroupPage, IdentityObservation, UserPage


class IdentityDirectoryStore(Protocol):
    async def observe(self, observation: IdentityObservation) -> None: ...

    async def search_groups(self, scope: DirectoryScope) -> GroupPage: ...

    async def search_users(self, scope: DirectoryScope) -> UserPage: ...
