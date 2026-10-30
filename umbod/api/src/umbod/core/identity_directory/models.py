from datetime import datetime
from uuid import uuid4
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from typing_extensions import Self

Nonblank = Annotated[str, StringConstraints(strict=True, pattern=r"\S")]
EmailVerification = Literal["unknown", "verified", "unverified"]


class DirectoryModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IdentityObservation(DirectoryModel):
    issuer: Nonblank
    subject: Nonblank
    claim: Nonblank
    groups: tuple[Nonblank, ...]
    name: str
    email: str
    email_verification: EmailVerification
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_email_verification(self) -> Self:
        if not self.email and self.email_verification != "unknown":
            raise ValueError("Email verification requires an email")
        return self


class ObservedGroup(DirectoryModel):
    value: Nonblank
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime


class ObservedUser(DirectoryModel):
    user_id: Nonblank
    issuer: Nonblank
    subject: Nonblank
    name: str
    email: str
    email_verification: EmailVerification
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime


class StoredUser(ObservedUser):
    name_seen_at: AwareDatetime
    email_seen_at: AwareDatetime


class DirectoryScope(DirectoryModel):
    issuer: str
    claim: str
    query: str
    limit: int = Field(ge=1, le=100)


class GroupPage(DirectoryModel):
    issuer: str
    claim: str
    groups: tuple[ObservedGroup, ...]
    has_more: bool


class UserPage(DirectoryModel):
    issuer: str
    users: tuple[ObservedUser, ...]
    has_more: bool


def new_user(observation: IdentityObservation) -> StoredUser:
    return StoredUser(
        user_id=uuid4().hex,
        issuer=observation.issuer,
        subject=observation.subject,
        name=observation.name,
        email=observation.email,
        email_verification=observation.email_verification,
        first_seen_at=observation.observed_at,
        last_seen_at=observation.observed_at,
        name_seen_at=observation.observed_at,
        email_seen_at=observation.observed_at,
    )


def merge_user(current: StoredUser, observation: IdentityObservation) -> StoredUser:
    updates: dict[str, str | datetime] = {
        "first_seen_at": min(current.first_seen_at, observation.observed_at),
        "last_seen_at": max(current.last_seen_at, observation.observed_at),
    }
    if observation.name and (
        not current.name or observation.observed_at >= current.name_seen_at
    ):
        updates.update(name=observation.name, name_seen_at=observation.observed_at)
    if observation.email and (
        not current.email or observation.observed_at >= current.email_seen_at
    ):
        verification = observation.email_verification
        if observation.email == current.email and verification == "unknown":
            verification = current.email_verification
        updates.update(
            email=observation.email,
            email_verification=verification,
            email_seen_at=observation.observed_at,
        )
    return StoredUser.model_validate({**current.model_dump(), **updates})
