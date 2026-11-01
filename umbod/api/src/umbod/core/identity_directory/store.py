import json
from typing import Optional

from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DatabaseSession,
    Equals,
    Query,
    TransactionMode,
    Unordered,
    UpsertCommand,
)
from .models import (
    DirectoryScope,
    GroupPage,
    IdentityObservation,
    ObservedGroup,
    ObservedUser,
    UserPage,
    merge_user,
    new_user,
)
from .user_models import (
    ObservedUserIdentity,
    ObservedUserProfile,
    SubjectUsersLookup,
    ScopedUserSearch,
    UserLookup,
    UserSearchPage,
    UserSearchResult,
    normalized_name,
)
from .schema import (
    DirectoryKey,
    GROUP_CLAIM,
    GROUP_ISSUER,
    GROUP_KEY,
    GROUP_TABLE,
    GroupRecord,
    USER_ISSUER,
    USER_KEY,
    USER_TABLE,
    UserRecord,
)


def identity_key(*values: str) -> str:
    return json.dumps(values, ensure_ascii=True, separators=(",", ":"))


class SessionObservedUsers:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    async def search_user_names(self, search: ScopedUserSearch) -> UserSearchPage:
        rows = await self._session.find_many(
            USER_TABLE,
            Query(Equals(USER_ISSUER, search.issuer), AllFields(), Unordered()),
        )
        query = normalized_name(search.query)
        users = sorted(
            (
                UserSearchResult(user_id=row.payload.user_id, name=row.payload.name)
                for row in rows
                if row.payload.subject not in search.excluded_subjects
                and query in normalized_name(row.payload.name)
            ),
            key=lambda user: (normalized_name(user.name), user.user_id),
        )
        return UserSearchPage(
            users=tuple(users[: search.limit]), has_more=len(users) > search.limit
        )

    async def find_user_identity(
        self, lookup: UserLookup
    ) -> Optional[ObservedUserIdentity]:
        rows = await self._session.find_many(
            USER_TABLE,
            Query(Equals(USER_ISSUER, lookup.issuer), AllFields(), Unordered()),
        )
        for row in rows:
            user = row.payload
            if user.user_id == lookup.user_id:
                return ObservedUserIdentity(
                    user_id=user.user_id, issuer=user.issuer, subject=user.subject
                )
        return None

    async def find_subject_users(
        self, lookup: SubjectUsersLookup,
    ) -> tuple[ObservedUserProfile, ...]:
        if not lookup.subjects:
            return ()
        rows = await self._session.find_many(
            USER_TABLE,
            Query(Equals(USER_ISSUER, lookup.issuer), AllFields(), Unordered()),
        )
        return tuple(
            ObservedUserProfile(
                user_id=row.payload.user_id, issuer=row.payload.issuer,
                subject=row.payload.subject, name=row.payload.name,
            )
            for row in rows if row.payload.subject in lookup.subjects
        )


class DatabaseIdentityDirectory:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def observe(self, observation: IdentityObservation) -> None:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            key = identity_key(observation.issuer, observation.subject)
            existing = await session.find_one(
                USER_TABLE, Query(Equals(USER_KEY, key), AllFields(), Unordered())
            )
            user = (
                new_user(observation)
                if existing is None
                else merge_user(existing.payload, observation)
            )
            await session.upsert(
                USER_TABLE,
                UpsertCommand(
                    key=DirectoryKey(key=key),
                    row=UserRecord(key=key, issuer=observation.issuer, payload=user),
                ),
            )
            for value in sorted(set(observation.groups)):
                key = identity_key(observation.issuer, observation.claim, value)
                group = await session.find_one(
                    GROUP_TABLE, Query(Equals(GROUP_KEY, key), AllFields(), Unordered())
                )
                first = (
                    observation.observed_at
                    if group is None
                    else min(group.payload.first_seen_at, observation.observed_at)
                )
                last = (
                    observation.observed_at
                    if group is None
                    else max(group.payload.last_seen_at, observation.observed_at)
                )
                await session.upsert(
                    GROUP_TABLE,
                    UpsertCommand(
                        key=DirectoryKey(key=key),
                        row=GroupRecord(
                            key=key,
                            issuer=observation.issuer,
                            claim=observation.claim,
                            payload=ObservedGroup(
                                value=value, first_seen_at=first, last_seen_at=last
                            ),
                        ),
                    ),
                )

    async def search_groups(self, scope: DirectoryScope) -> GroupPage:
        if not scope.issuer.strip() or not scope.claim.strip():
            return GroupPage(
                issuer=scope.issuer, claim=scope.claim, groups=(), has_more=False
            )
        async with self._database.read_session() as session:
            rows = await session.find_many(
                GROUP_TABLE,
                Query(
                    AllOf(
                        (
                            Equals(GROUP_ISSUER, scope.issuer),
                            Equals(GROUP_CLAIM, scope.claim),
                        )
                    ),
                    AllFields(),
                    Unordered(),
                ),
            )
        groups = sorted(
            (
                row.payload
                for row in rows
                if scope.query.casefold() in row.payload.value.casefold()
            ),
            key=lambda group: group.value,
        )
        return GroupPage(
            issuer=scope.issuer,
            claim=scope.claim,
            groups=tuple(groups[: scope.limit]),
            has_more=len(groups) > scope.limit,
        )

    async def search_user_names(self, search: ScopedUserSearch) -> UserSearchPage:
        async with self._database.read_session() as session:
            return await SessionObservedUsers(session).search_user_names(search)

    async def find_user_identity(
        self, lookup: UserLookup,
    ) -> Optional[ObservedUserIdentity]:
        async with self._database.read_session() as session:
            return await SessionObservedUsers(session).find_user_identity(lookup)

    async def find_subject_users(
        self, lookup: SubjectUsersLookup,
    ) -> tuple[ObservedUserProfile, ...]:
        async with self._database.read_session() as session:
            return await SessionObservedUsers(session).find_subject_users(lookup)

    async def search_users(self, scope: DirectoryScope) -> UserPage:
        if not scope.issuer.strip():
            return UserPage(issuer=scope.issuer, users=(), has_more=False)
        async with self._database.read_session() as session:
            rows = await session.find_many(
                USER_TABLE,
                Query(Equals(USER_ISSUER, scope.issuer), AllFields(), Unordered()),
            )
        users = sorted(
            (
                row.payload
                for row in rows
                if any(
                    scope.query.casefold() in field.casefold()
                    for field in (
                        row.payload.name,
                        row.payload.email,
                        row.payload.subject,
                    )
                )
            ),
            key=lambda user: (user.subject, user.user_id),
        )
        public_users = tuple(
            ObservedUser.model_validate(
                user.model_dump(exclude={"name_seen_at", "email_seen_at"})
            )
            for user in users[: scope.limit]
        )
        return UserPage(
            issuer=scope.issuer, users=public_users, has_more=len(users) > scope.limit
        )
