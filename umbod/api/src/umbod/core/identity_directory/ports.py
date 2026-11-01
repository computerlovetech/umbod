from typing import Optional, Protocol

from umbod.core.callers import CallerContext, SubjectIdentity

from .models import DirectoryScope, GroupPage, IdentityObservation, UserPage


from .user_models import (
    ObservedUserIdentity,
    ObservedUserProfile,
    SubjectUsersLookup,
    ScopedUserSearch,
    UserLookup,
    UserSearchPage,
)


class ObservedUserDirectory(Protocol):
    async def find_subject_users(
        self, lookup: SubjectUsersLookup,
    ) -> tuple[ObservedUserProfile, ...]: ...

    async def search_user_names(self, search: ScopedUserSearch) -> UserSearchPage: ...

    async def find_user_identity(
        self, lookup: UserLookup
    ) -> Optional[ObservedUserIdentity]: ...


class ObservedUserResolver(Protocol):
    async def resolve(self, caller: CallerContext, user_id: str) -> SubjectIdentity: ...


class IdentityDirectoryStore(Protocol):
    async def observe(self, observation: IdentityObservation) -> None: ...

    async def search_groups(self, scope: DirectoryScope) -> GroupPage: ...

    async def search_users(self, scope: DirectoryScope) -> UserPage: ...
