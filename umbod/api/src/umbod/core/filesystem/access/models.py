from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from ..browsing import NodeSummary
from ..models import AccessGrant, Principal


class CallerPermissions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    can_discover: bool
    can_read: bool
    can_write: bool
    can_delete: bool = Field(description="Effective delete permission and file deletion support; directories cannot be deleted.")
    can_share: bool


class AvailableVisibility(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["available"]
    scope: Literal["direct_node_policy"] = Field(description="Owner and complete direct-node grants only; no inherited grants or administrator override. Recursive flags do not imply inheritance.")
    owner: Principal
    grants: tuple[AccessGrant, ...]
    group_members_expanded: Literal[False] = Field(description="Group grants are represented as principals, never as an expanded audience.")

    @field_serializer("grants", when_used="json")
    def serialize_grants(self, grants: tuple[AccessGrant, ...]) -> list[dict[str, object]]:
        return [
            {**grant.model_dump(mode="json"), "permissions": sorted(permission.value for permission in grant.permissions)}
            for grant in sorted(grants, key=lambda grant: (
                grant.principal.type.value, grant.principal.issuer, grant.principal.id, str(grant.node_id),
            ))
        ]


class RestrictedVisibility(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["restricted"]


class UnavailableVisibility(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["unavailable"]


Visibility = Annotated[
    Union[AvailableVisibility, RestrictedVisibility, UnavailableVisibility], Field(discriminator="type"),
]


class CallerNodeSummary(NodeSummary):
    permissions: CallerPermissions = Field(description="Effective direct-node rights after discover authorization; flags do not promise operation support.")
    visible_to: Visibility
