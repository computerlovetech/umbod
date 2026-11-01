from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from umbod.core.groups.models import GroupDescription, RegisterGroup
from umbod.core.identity_directory.user_models import SearchText, UserIdentifier

from ..models import AccessGrant, Node, NodeId, Ownership, Permission


class GroupSharingTarget(RegisterGroup):
    type: Literal["group"]


class UserSharingTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["user"]
    user_id: UserIdentifier


SharingTarget = Annotated[
    GroupSharingTarget | UserSharingTarget, Field(discriminator="type"),
]


class ShareNodePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recipient: SharingTarget
    permissions: frozenset[Permission] = Field(min_length=1)

    @field_serializer("permissions", when_used="json")
    def serialize_permissions(self, permissions: frozenset[Permission]) -> list[str]:
        return sorted(permission.value for permission in permissions)


class ShareNodeResult(ShareNodePolicy):
    node_id: NodeId
    changed: bool


class GroupSharingRecipient(GroupSharingTarget):
    label: str


class UserSharingRecipient(UserSharingTarget):
    label: str


SharingRecipient = Annotated[
    GroupSharingRecipient | UserSharingRecipient, Field(discriminator="type"),
]


class SharingGrantSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recipient: SharingRecipient
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


SharingRecipientType = Literal["group", "user"]


class SharingScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    recipient_types: frozenset[SharingRecipientType] = Field(min_length=1)


class SharingRecipientSearchQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: SearchText
    scope: SharingScope


class SharingRecipientSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recipients: tuple[SharingRecipient, ...]
    has_more: bool


class ReplaceNodePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recipient_type: SharingRecipientType
    expected_revision: str
    grants: tuple[ShareNodePolicy, ...]

    @model_validator(mode="after")
    def validate_targets(self) -> Self:
        identities = set()
        for grant in self.grants:
            target = grant.recipient
            if target.type != self.recipient_type:
                raise ValueError("Policy targets must match recipient type")
            identifier = target.group_id if isinstance(target, GroupSharingTarget) else target.user_id
            identities.add((target.type, identifier))
        if len(identities) != len(self.grants):
            raise ValueError("Policy keys must be unique")
        return self


class NodePolicyView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: NodeId
    revision: str
    grants: tuple[SharingGrantSummary, ...]
    blocked_recipients: tuple[SharingTarget, ...]


class NodePolicyState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node: Node
    ownership: Ownership
    grants: tuple[AccessGrant, ...]
    registered_group_ids: frozenset[str]
