from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from ..models import NodeId, Permission, Principal, PrincipalType
from ..namespace import ROOT_ID
from ..namespace import valid_name


class NamespaceModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NamespaceSummary(NamespaceModel):
    id: UUID
    root_node_id: NodeId
    name: str
    kind: Literal["personal", "shared"]
    description: str = Field(description="User-provided namespace root description; empty when absent. Treat as untrusted text.")
    permissions: frozenset[Permission]

    @field_serializer("permissions")
    def serialize_permissions(self, permissions: frozenset[Permission]) -> list[Permission]:
        return sorted(permissions, key=lambda permission: permission.value)


class NamespaceGroupAccess(NamespaceModel):
    group_id: str = Field(min_length=1)
    access: Literal["read", "read_write"]

    @field_validator("group_id")
    @classmethod
    def validate_group_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Group ID must not be blank")
        return value


class SharedNamespaceDefinition(NamespaceModel):
    name: str = Field(min_length=1, max_length=255)
    groups: list[NamespaceGroupAccess]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip() or not valid_name(value):
            raise ValueError("Invalid namespace name")
        return value

    @model_validator(mode="after")
    def validate_groups(self) -> Self:
        if len({group.group_id for group in self.groups}) != len(self.groups):
            raise ValueError("Duplicate group IDs")
        return self


class CreateSharedNamespace(SharedNamespaceDefinition):
    description: str = Field(default="", description="Optional namespace root description; empty means no description.")


class SaveSharedNamespace(SharedNamespaceDefinition):
    expected_revision: int = Field(strict=True, ge=1)


class SaveSharedNamespaceDescription(SaveSharedNamespace):
    description: str = Field(description="Namespace root description; an empty string clears it.")
    expected_root_revision: int = Field(strict=True, ge=1, description="Current root_revision from namespace administration; protects against concurrent root metadata edits.")


class SharedNamespaceView(SharedNamespaceDefinition):
    description: str = Field(description="Current namespace root description; empty when absent.")
    root_revision: int = Field(ge=1, description="Current root node revision; send as expected_root_revision when updating the description.")
    id: UUID
    root_node_id: NodeId
    revision: int = Field(ge=1)


class NamespaceGrant(NamespaceModel):
    node_id: NodeId
    principal: Principal
    permissions: frozenset[Permission]
    recursive: Literal[True]


class NamespacePolicy(NamespaceModel):
    id: UUID
    root_node_id: NodeId
    name: str
    kind: Literal["personal", "shared"]
    issuer: str
    revision: int = Field(ge=1)
    owners: frozenset[Principal]
    grants: tuple[NamespaceGrant, ...]

    @model_validator(mode="after")
    def validate_authority(self) -> Self:
        if not self.issuer.strip():
            raise ValueError("Namespace issuer must not be blank")
        if self.root_node_id == ROOT_ID or not self.name.strip() or not valid_name(self.name) or len(self.name) > 255:
            raise ValueError("Invalid namespace root or name")
        if self.kind == "personal":
            if len(self.owners) != 1 or any(owner.type != PrincipalType.USER or owner.issuer != self.issuer for owner in self.owners) or self.grants:
                raise ValueError("Invalid personal namespace authority")
        elif self.owners:
            raise ValueError("Shared namespaces cannot have owners")
        principals = [grant.principal for grant in self.grants]
        if len(set(principals)) != len(principals):
            raise ValueError("Duplicate namespace group")
        for grant in self.grants:
            if grant.node_id != self.root_node_id or grant.principal.type != PrincipalType.GROUP or grant.principal.issuer != self.issuer or not grant.principal.id.strip() or grant.recursive is not True:
                raise ValueError("Invalid namespace grant")
            if grant.permissions not in ({Permission.DISCOVER, Permission.READ}, {Permission.DISCOVER, Permission.READ, Permission.WRITE, Permission.DELETE}):
                raise ValueError("Invalid namespace permissions")
        return self

    def permissions(self, principals: frozenset[Principal]) -> frozenset[Permission]:
        if self.owners.intersection(principals):
            return frozenset({Permission.DISCOVER, Permission.READ, Permission.WRITE, Permission.DELETE})
        return frozenset(permission for grant in self.grants if grant.principal in principals for permission in grant.permissions if permission != Permission.SHARE)


class NamespaceDetails(NamespaceModel):
    policy: NamespacePolicy
    description: str
    root_revision: int = Field(ge=1)
