from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ..models import NodeId, Permission, Principal, PrincipalType


class ResolvedIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user: Principal
    groups: frozenset[Principal]

    @model_validator(mode="after")
    def validate_principal_types(self) -> Self:
        if self.user.type != PrincipalType.USER:
            raise ValueError("Resolved user must be a USER principal")
        if any(group.type != PrincipalType.GROUP for group in self.groups):
            raise ValueError("Resolved groups must be GROUP principals")
        return self

    @property
    def principals(self) -> frozenset[Principal]:
        return self.groups | {self.user}


class UnresolvedIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AuthorizationDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: NodeId
    permission: Permission
    allowed: bool
