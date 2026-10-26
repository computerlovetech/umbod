from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence.query import (
    Field,
    Fields,
    KeyCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
)


class PermissionGroupRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str


class PermissionGroupKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str


class GroupIdResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str


GROUP_IDENTITY = TableIdentity("mcp_permission_groups")
GROUP_ID = Field[PermissionGroupRecord, str](GROUP_IDENTITY, "group_id", TextCodec())
GROUP_TABLE = Table(
    GROUP_IDENTITY,
    RowCodec(
        PermissionGroupRecord,
        cast(tuple[Field[PermissionGroupRecord, object], ...], (GROUP_ID,)),
    ),
    KeyCodec(
        PermissionGroupKey,
        cast(tuple[Field[PermissionGroupRecord, object], ...], (GROUP_ID,)),
    ),
)
GROUP_ID_PROJECTION = Fields(
    GroupIdResult,
    cast(tuple[Field[PermissionGroupRecord, object], ...], (GROUP_ID,)),
)

GROUPS = GROUP_TABLE
