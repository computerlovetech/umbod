from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ..models import Permission, Principal, PrincipalType


class RootBootstrapGrant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    principal: Principal
    permissions: frozenset[Permission]

    @model_validator(mode="after")
    def validate_principal(self) -> Self:
        if self.principal.type not in (PrincipalType.USER, PrincipalType.GROUP):
            raise ValueError("Bootstrap grants require USER or GROUP principals")
        if not self.principal.issuer.strip() or not self.principal.id.strip():
            raise ValueError("Bootstrap principals require nonblank issuer and ID")
        return self


class RootBootstrapSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    grants: tuple[RootBootstrapGrant, ...]

    @model_validator(mode="after")
    def validate_unique_principals(self) -> Self:
        principals = [grant.principal for grant in self.grants]
        if len(set(principals)) != len(principals):
            raise ValueError("Duplicate bootstrap principal")
        return self
