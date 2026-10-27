from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..models import AccessGrant, Node, Ownership, Permission


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


class SaveRootGroupPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_revision: str
    groups: tuple[GroupPolicy, ...]

    @model_validator(mode="after")
    def unique_groups(self) -> Self:
        keys = {group.group_id for group in self.groups}
        if len(keys) != len(self.groups):
            raise ValueError("Policy keys must be unique")
        return self


class RootPolicyStatus(StrEnum):
    UNINITIALIZED = "uninitialized"
    READY = "ready"
    CONFLICT = "conflict"


class RootGroupPolicyView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RootPolicyStatus
    revision: str
    groups: tuple[GroupPolicy, ...]
    blocked_group_ids: tuple[str, ...]


class RootPolicyState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    roots: tuple[Node, ...]
    owners: tuple[Ownership, ...]
    grants: tuple[AccessGrant, ...]
    has_children: bool
    malformed_root: bool
