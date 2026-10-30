from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from ..group_policy import GroupPolicy
from ..models import AccessGrant, Node, Ownership


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
