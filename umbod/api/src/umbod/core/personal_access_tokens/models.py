from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    model_validator,
)


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Value must not be blank")
    return value


def exact_scope(value: str) -> str:
    if "*" in value or any(character.isspace() for character in value):
        raise ValueError("Scopes must be exact and contain no whitespace or wildcards")
    return value


def unique_scopes(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values or len(values) > 64 or len(set(values)) != len(values):
        raise ValueError("Scopes must contain between 1 and 64 unique entries")
    return values


def utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


BoundedText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=256),
    AfterValidator(nonblank),
]
Scope = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=128),
    AfterValidator(nonblank),
    AfterValidator(exact_scope),
]
Scopes = Annotated[tuple[Scope, ...], AfterValidator(unique_scopes)]
TokenId = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{32}$")]
UtcDatetime = Annotated[AwareDatetime, AfterValidator(utc)]


class TokenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class TokenOwner(TokenModel):
    issuer: Annotated[
        str,
        StringConstraints(strict=True, min_length=1, max_length=4096),
        AfterValidator(nonblank),
    ]
    subject: Annotated[
        str,
        StringConstraints(strict=True, min_length=1, max_length=4096),
        AfterValidator(nonblank),
    ]


class PersonalAccessTokenPolicy(TokenModel):
    allowed_scopes: Scopes


class IssuePersonalAccessToken(TokenModel):
    name: BoundedText
    audience: BoundedText
    scopes: Scopes
    expires_at: UtcDatetime


class ValidatePersonalAccessToken(TokenModel):
    token: SecretStr
    audience: BoundedText
    required_scopes: Scopes


class PersonalAccessTokenStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class PersonalAccessTokenMetadata(TokenModel):
    token_id: TokenId
    owner: TokenOwner
    name: BoundedText
    audience: BoundedText
    scopes: Scopes
    created_at: UtcDatetime
    expires_at: UtcDatetime
    status: PersonalAccessTokenStatus

    @model_validator(mode="after")
    def validate_lifetime(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("Expiry must be after creation")
        return self


class IssuedPersonalAccessToken(TokenModel):
    token: SecretStr
    metadata: PersonalAccessTokenMetadata


class GeneratedPersonalAccessToken(TokenModel):
    token_id: TokenId
    token: SecretStr


class StoredPersonalAccessToken(TokenModel):
    metadata: PersonalAccessTokenMetadata
    digest: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] = Field(
        repr=False, exclude=True
    )
