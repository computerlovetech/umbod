from datetime import timezone
from typing import Self, cast

from pydantic import BaseModel, ConfigDict, model_validator

from umbod.core.persistence import (
    Field,
    Fields,
    IntegerCodec,
    KeyCodec,
    PydanticJsonCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
)
from ..models import AccessGrant, EmptyContent, Node, NodeKind, Ownership, RootParent
from ..namespace import ROOT_ID, valid_name


class NodeKey(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str


class NodeRecord(NodeKey):
    parent_id: str
    name: str
    revision: int
    payload: Node

    @model_validator(mode="after")
    def validate_node(self) -> Self:
        node = self.payload
        parent = "" if isinstance(node.parent_id, RootParent) else str(node.parent_id)
        if (self.node_id, self.parent_id, self.name, self.revision) != (
            str(node.id),
            parent,
            node.name,
            node.revision,
        ):
            raise ValueError("Node index mismatch")
        if isinstance(node.parent_id, RootParent):
            if node.id != ROOT_ID or node.name != "" or node.kind != NodeKind.DIRECTORY:
                raise ValueError("Invalid namespace root")
        elif (
            node.id == ROOT_ID or node.id == node.parent_id or not valid_name(node.name)
        ):
            raise ValueError("Invalid namespace node")
        if node.kind == NodeKind.DIRECTORY and not isinstance(
            node.content, EmptyContent
        ):
            raise ValueError("Directory has content")
        for timestamp in (node.created_at, node.updated_at):
            if timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
                raise ValueError("Node timestamps must be UTC")
        if node.updated_at < node.created_at:
            raise ValueError("Invalid node timestamps")
        return self


class OwnershipRecord(NodeKey):
    payload: Ownership

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.node_id != str(self.payload.node_id):
            raise ValueError("Ownership index mismatch")
        return self


class GrantKey(NodeKey):
    principal_type: str
    issuer: str
    principal_id: str


class GrantRecord(GrantKey):
    payload: AccessGrant

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        grant = self.payload
        if (self.node_id, self.principal_type, self.issuer, self.principal_id) != (
            str(grant.node_id),
            grant.principal.type.value,
            grant.principal.issuer,
            grant.principal.id,
        ):
            raise ValueError("Grant index mismatch")
        return self


NODE_IDENTITY = TableIdentity("filesystem_nodes")
NODE_ID = Field[NodeRecord, str](NODE_IDENTITY, "node_id", TextCodec())
NODE_PARENT = Field[NodeRecord, str](NODE_IDENTITY, "parent_id", TextCodec())
NODE_NAME = Field[NodeRecord, str](NODE_IDENTITY, "name", TextCodec())
NODE_REVISION = Field[NodeRecord, int](NODE_IDENTITY, "revision", IntegerCodec())
NODE_PAYLOAD = Field[NodeRecord, Node](
    NODE_IDENTITY, "payload", PydanticJsonCodec(Node)
)
NODE_TABLE = Table(
    NODE_IDENTITY,
    RowCodec(
        NodeRecord,
        cast(
            tuple[Field[NodeRecord, object], ...],
            (NODE_ID, NODE_PARENT, NODE_NAME, NODE_REVISION, NODE_PAYLOAD),
        ),
    ),
    KeyCodec(NodeKey, cast(tuple[Field[NodeRecord, object], ...], (NODE_ID,))),
)
NODE_KEY_PROJECTION = Fields(
    NodeKey, cast(tuple[Field[NodeRecord, object], ...], (NODE_ID,)),
)
OWNER_IDENTITY = TableIdentity("filesystem_ownership")
OWNER_NODE = Field[OwnershipRecord, str](OWNER_IDENTITY, "node_id", TextCodec())
OWNER_PAYLOAD = Field[OwnershipRecord, Ownership](
    OWNER_IDENTITY, "payload", PydanticJsonCodec(Ownership)
)
OWNER_TABLE = Table(
    OWNER_IDENTITY,
    RowCodec(
        OwnershipRecord,
        cast(tuple[Field[OwnershipRecord, object], ...], (OWNER_NODE, OWNER_PAYLOAD)),
    ),
    KeyCodec(NodeKey, cast(tuple[Field[OwnershipRecord, object], ...], (OWNER_NODE,))),
)
GRANT_IDENTITY = TableIdentity("filesystem_grants")
GRANT_NODE = Field[GrantRecord, str](GRANT_IDENTITY, "node_id", TextCodec())
GRANT_TYPE = Field[GrantRecord, str](GRANT_IDENTITY, "principal_type", TextCodec())
GRANT_ISSUER = Field[GrantRecord, str](GRANT_IDENTITY, "issuer", TextCodec())
GRANT_PRINCIPAL = Field[GrantRecord, str](GRANT_IDENTITY, "principal_id", TextCodec())
GRANT_PAYLOAD = Field[GrantRecord, AccessGrant](
    GRANT_IDENTITY, "payload", PydanticJsonCodec(AccessGrant)
)
GRANT_TABLE = Table(
    GRANT_IDENTITY,
    RowCodec(
        GrantRecord,
        cast(
            tuple[Field[GrantRecord, object], ...],
            (GRANT_NODE, GRANT_TYPE, GRANT_ISSUER, GRANT_PRINCIPAL, GRANT_PAYLOAD),
        ),
    ),
    KeyCodec(
        GrantKey,
        cast(
            tuple[Field[GrantRecord, object], ...],
            (GRANT_NODE, GRANT_TYPE, GRANT_ISSUER, GRANT_PRINCIPAL),
        ),
    ),
)
