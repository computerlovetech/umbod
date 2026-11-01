from typing import Annotated

from pydantic import Field, StringConstraints

from .models import DirectoryModel, Nonblank

SearchText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200),
]
UserIdentifier = Annotated[
    str, StringConstraints(strict=True, pattern=r"\S", max_length=200)
]


class UserSearchQuery(DirectoryModel):
    query: SearchText
    excluded_subjects: frozenset[Nonblank]
    limit: int = Field(strict=True, ge=1, le=100)


class ScopedUserSearch(UserSearchQuery):
    issuer: Nonblank


class UserLookup(DirectoryModel):
    issuer: Nonblank
    user_id: UserIdentifier


class UserSearchResult(DirectoryModel):
    user_id: UserIdentifier
    name: str


class UserSearchPage(DirectoryModel):
    users: tuple[UserSearchResult, ...]
    has_more: bool


class ObservedUserIdentity(DirectoryModel):
    user_id: UserIdentifier
    issuer: Nonblank
    subject: Nonblank


class SubjectUsersLookup(DirectoryModel):
    issuer: Nonblank
    subjects: frozenset[Nonblank]


class ObservedUserProfile(ObservedUserIdentity):
    name: str


def normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()
