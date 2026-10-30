from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from umbod.core.groups.models import GroupDescription, RegisterGroup

from ..group_policy import GroupPolicy
from ..models import AccessGrant, Node, NodeId, Ownership, Permission


class ShareNodeGroupResult(GroupPolicy):
    node_id: NodeId
    changed: bool

    @field_serializer("permissions", when_used="json")
    def serialize_permissions(self, permissions: frozenset[Permission]) -> list[str]:
        return sorted(permission.value for permission in permissions)


class GroupSharingRecipient(RegisterGroup):
    type: Literal["group"]
    label: str


class SharingGrantSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recipient: GroupSharingRecipient
    permissions: frozenset[Permission] = Field(min_length=1)

    @field_serializer("permissions", when_used="json")
    def serialize_permissions(self, permissions: frozenset[Permission]) -> list[str]:
        return sorted(permission.value for permission in permissions)


class ShareableNodeSharingSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: NodeId
    can_share: Literal[True]
    grants: tuple[SharingGrantSummary, ...]


class RestrictedNodeSharingSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: NodeId
    can_share: Literal[False]


NodeSharingSummary = Annotated[
    ShareableNodeSharingSummary | RestrictedNodeSharingSummary,
    Field(discriminator="can_share"),
]


class NodeSharingSummaries(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: tuple[NodeSharingSummary, ...]


class EligibleSharingGroup(RegisterGroup):
    label: str
    description: GroupDescription


class EligibleSharingGroups(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    groups: tuple[EligibleSharingGroup, ...]


class ReplaceNodeGroupPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_revision: str
    groups: tuple[GroupPolicy, ...]

    @model_validator(mode="after")
    def unique_groups(self) -> Self:
        if len({group.group_id for group in self.groups}) != len(self.groups):
            raise ValueError("Policy keys must be unique")
        return self


class NodeGroupPolicyView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: NodeId
    revision: str
    groups: tuple[GroupPolicy, ...]
    blocked_group_ids: tuple[str, ...]


class NodePolicyState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node: Node
    ownership: Ownership
    grants: tuple[AccessGrant, ...]
    registered_group_ids: frozenset[str]
