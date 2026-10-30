from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.groups.models import Group

from umbod.core.persistence.query import (
    Field,
    Fields,
    KeyCodec,
    RowCodec,
    Table,
    TableIdentity,
    TextCodec,
    IntegerCodec,
)


class PermissionGroupRecord(Group):
    pass


class PermissionGroupKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str


class GroupIdResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str


GROUP_IDENTITY = TableIdentity("mcp_permission_groups")
GROUP_ID = Field[PermissionGroupRecord, str](GROUP_IDENTITY, "group_id", TextCodec())
GROUP_LABEL = Field[PermissionGroupRecord, str](GROUP_IDENTITY, "label", TextCodec())
GROUP_DESCRIPTION = Field[PermissionGroupRecord, str](GROUP_IDENTITY, "description", TextCodec())
GROUP_REVISION = Field[PermissionGroupRecord, int](GROUP_IDENTITY, "revision", IntegerCodec())
GROUP_TABLE = Table(
    GROUP_IDENTITY,
    RowCodec(
        PermissionGroupRecord,
        cast(tuple[Field[PermissionGroupRecord, object], ...], (GROUP_ID, GROUP_LABEL, GROUP_DESCRIPTION, GROUP_REVISION)),
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
