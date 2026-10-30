import asyncio

from umbod.core.identity_directory.models import (
    DirectoryScope,
    GroupPage,
    IdentityObservation,
    ObservedGroup,
    ObservedUser,
    StoredUser,
    UserPage,
    merge_user,
    new_user,
)


class InMemoryIdentityDirectory:
    def __init__(self) -> None:
        self.users: dict[tuple[str, str], StoredUser] = {}
        self.groups: dict[tuple[str, str, str], ObservedGroup] = {}
        self.lock = asyncio.Lock()

    async def observe(self, observation: IdentityObservation) -> None:
        async with self.lock:
            key = (observation.issuer, observation.subject)
            current = self.users.get(key)
            self.users[key] = (
                new_user(observation)
                if current is None
                else merge_user(current, observation)
            )
            for value in observation.groups:
                group_key = (observation.issuer, observation.claim, value)
                group = self.groups.get(group_key)
                self.groups[group_key] = ObservedGroup(
                    value=value,
                    first_seen_at=observation.observed_at
                    if group is None
                    else min(group.first_seen_at, observation.observed_at),
                    last_seen_at=observation.observed_at
                    if group is None
                    else max(group.last_seen_at, observation.observed_at),
                )

    async def search_groups(self, scope: DirectoryScope) -> GroupPage:
        groups = sorted(
            (
                group
                for (issuer, claim, _), group in self.groups.items()
                if issuer == scope.issuer
                and claim == scope.claim
                and scope.query.casefold() in group.value.casefold()
            ),
            key=lambda group: group.value,
        )
        return GroupPage(
            issuer=scope.issuer,
            claim=scope.claim,
            groups=tuple(groups[: scope.limit]),
            has_more=len(groups) > scope.limit,
        )

    async def search_users(self, scope: DirectoryScope) -> UserPage:
        users = sorted(
            (
                user
                for (issuer, _), user in self.users.items()
                if issuer == scope.issuer
                and any(
                    scope.query.casefold() in value.casefold()
                    for value in (user.name, user.email, user.subject)
                )
            ),
            key=lambda user: (user.subject, user.user_id),
        )
        return UserPage(
            issuer=scope.issuer,
            users=tuple(
                ObservedUser.model_validate(
                    user.model_dump(exclude={"name_seen_at", "email_seen_at"})
                )
                for user in users[: scope.limit]
            ),
            has_more=len(users) > scope.limit,
        )
