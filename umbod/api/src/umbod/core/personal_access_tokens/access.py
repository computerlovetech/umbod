from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Self

from pydantic import Field, model_validator

from .models import BoundedText, PersonalAccessTokenPolicy, Scopes, TokenModel

TELEMETRY_TOKEN_AUDIENCE = "umbod:telemetry"
TELEMETRY_INGEST_SCOPE = "telemetry:write"


class PersonalAccessTokenResource(StrEnum):
    TELEMETRY = "telemetry"


class PersonalAccessTokenPermission(StrEnum):
    WRITE = "write"


class PersonalAccessTokenGrant(TokenModel):
    resource: PersonalAccessTokenResource
    permission: PersonalAccessTokenPermission


class PersonalAccessTokenAccess(TokenModel):
    grants: Annotated[tuple[PersonalAccessTokenGrant, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_unique_resources(self) -> Self:
        resources = tuple(grant.resource for grant in self.grants)
        if len(set(resources)) != len(resources):
            raise ValueError("Access must contain unique resources")
        return self


class ResolvedPersonalAccessTokenAccess(TokenModel):
    audience: BoundedText
    scopes: Scopes


class UnsupportedPersonalAccessTokenAccess(ValueError):
    pass


_ACCESS_RULES: Mapping[
    tuple[PersonalAccessTokenResource, PersonalAccessTokenPermission],
    ResolvedPersonalAccessTokenAccess,
] = MappingProxyType(
    {
        (
            PersonalAccessTokenResource.TELEMETRY,
            PersonalAccessTokenPermission.WRITE,
        ): ResolvedPersonalAccessTokenAccess(
            audience=TELEMETRY_TOKEN_AUDIENCE, scopes=(TELEMETRY_INGEST_SCOPE,)
        ),
    }
)


def resolve_personal_access_token_access(
    access: PersonalAccessTokenAccess,
) -> ResolvedPersonalAccessTokenAccess:
    try:
        rules = tuple(
            _ACCESS_RULES[(grant.resource, grant.permission)] for grant in access.grants
        )
    except KeyError:
        raise UnsupportedPersonalAccessTokenAccess(
            "Unsupported personal access token access"
        ) from None
    audiences = frozenset(rule.audience for rule in rules)
    if len(audiences) != 1:
        raise UnsupportedPersonalAccessTokenAccess(
            "Unsupported personal access token access"
        )
    return ResolvedPersonalAccessTokenAccess(
        audience=next(iter(audiences)),
        scopes=tuple(dict.fromkeys(scope for rule in rules for scope in rule.scopes)),
    )


def personal_access_token_policy() -> PersonalAccessTokenPolicy:
    return PersonalAccessTokenPolicy(
        allowed_scopes=tuple(
            dict.fromkeys(
                scope for rule in _ACCESS_RULES.values() for scope in rule.scopes
            )
        )
    )
