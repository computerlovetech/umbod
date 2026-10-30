from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import AccessGrant, Permission, PrincipalType


class GroupPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    group_id: str
    permissions: frozenset[Permission] = Field(min_length=1)

    @field_validator("group_id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Policy keys must be nonblank")
        return value


def editable_grant(grant: AccessGrant, issuer: str) -> bool:
    return (
        grant.principal.type == PrincipalType.GROUP
        and grant.principal.issuer == issuer
        and bool(grant.principal.id.strip())
        and bool(grant.permissions)
        and not grant.recursive
    )


def canonical_grants(grants: Sequence[AccessGrant]) -> list[dict[str, object]]:
    ordered = sorted(grants, key=lambda grant: (
        grant.principal.type, grant.principal.issuer, grant.principal.id,
    ))
    return [
        {
            **grant.model_dump(mode="json", exclude={"permissions"}),
            "permissions": sorted(grant.permissions),
        }
        for grant in ordered
    ]
