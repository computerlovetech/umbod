from umbod.core.callers import (
    AuthenticationProvenance,
    CallerContext,
    DeclaredIssuer,
    SubjectIdentity,
)

from .ports import ObservedUserDirectory
from .user_models import (
    ObservedUserProfile, SubjectUsersLookup, UserLookup, UserSearchPage,
    UserSearchQuery, ScopedUserSearch,
)


class UserSearchDenied(Exception):
    pass


class ObservedUserNotFound(Exception):
    pass


class ObservedUserService:
    def __init__(self, directory: ObservedUserDirectory, issuer: str) -> None:
        self._directory = directory
        self._issuer = issuer

    def _authorize(self, caller: CallerContext) -> None:
        subject = caller.subject
        if (
            caller.authentication != AuthenticationProvenance.UPSTREAM_VERIFIED
            or not isinstance(subject, SubjectIdentity)
            or not isinstance(subject.issuer, DeclaredIssuer)
            or not self._issuer.strip()
            or subject.issuer.value != self._issuer
            or not subject.subject.strip()
        ):
            raise UserSearchDenied()

    async def search(
        self, caller: CallerContext, query: UserSearchQuery
    ) -> UserSearchPage:
        self._authorize(caller)
        return await self._directory.search_user_names(
            ScopedUserSearch(
                issuer=self._issuer,
                query=query.query,
                limit=query.limit,
                excluded_subjects=query.excluded_subjects,
            )
        )

    async def profiles(
        self, caller: CallerContext, subjects: frozenset[str],
    ) -> tuple[ObservedUserProfile, ...]:
        self._authorize(caller)
        return await self._directory.find_subject_users(
            SubjectUsersLookup(issuer=self._issuer, subjects=subjects),
        )

    async def resolve(self, caller: CallerContext, user_id: str) -> SubjectIdentity:
        self._authorize(caller)
        lookup = UserLookup(issuer=self._issuer, user_id=user_id)
        identity = await self._directory.find_user_identity(lookup)
        if (
            identity is None
            or identity.issuer != self._issuer
            or identity.user_id != user_id
        ):
            raise ObservedUserNotFound()
        return SubjectIdentity(
            issuer=DeclaredIssuer(value=identity.issuer),
            subject=identity.subject,
        )
