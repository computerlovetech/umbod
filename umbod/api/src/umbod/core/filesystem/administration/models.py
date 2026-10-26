from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..models import AccessGrant, Node, NodeId, Ownership, Permission


class GroupPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issuer: str
    group_id: str
    permissions: frozenset[Permission] = Field(min_length=1)

    @field_validator("issuer", "group_id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Policy keys must be nonblank")
        return value


class SaveRootGroupPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_revision: str
    groups: tuple[GroupPolicy, ...]

    @model_validator(mode="after")
    def unique_groups(self) -> Self:
        keys = {(group.issuer, group.group_id) for group in self.groups}
        if len(keys) != len(self.groups):
            raise ValueError("Policy keys must be unique")
        return self


class RootPolicyStatus(StrEnum):
    UNINITIALIZED = "uninitialized"
    READY = "ready"
    CONFLICT = "conflict"


class ObservedGroupPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issuer: str
    group_id: str
    permissions: frozenset[Permission]


class RootGroupPolicyView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    root_id: NodeId
    status: RootPolicyStatus
    revision: str
    groups: tuple[ObservedGroupPolicy, ...]
    unmanaged_groups: tuple[ObservedGroupPolicy, ...]


class RootPolicyState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    roots: tuple[Node, ...]
    owners: tuple[Ownership, ...]
    grants: tuple[AccessGrant, ...]
    has_children: bool
    malformed_root: bool
