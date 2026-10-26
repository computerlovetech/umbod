from umbod.core.groups.stores.schema import (
    GROUP_ID as GROUP_ID,
    GROUP_IDENTITY as GROUP_IDENTITY,
    GROUP_ID_PROJECTION as GROUP_ID_PROJECTION,
    GROUP_TABLE as GROUP_TABLE,
    GroupIdResult as GroupIdResult,
    PermissionGroupKey as PermissionGroupKey,
    PermissionGroupRecord as PermissionGroupRecord,
)
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


class GroupConnectorPermissionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str
    connector_id: str


class GroupConnectorPermissionKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str
    connector_id: str


class GroupCapabilityPermissionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str
    connector_id: str
    capability_kind: str
    capability_key: str


class GroupCapabilityPermissionKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str
    connector_id: str
    capability_kind: str
    capability_key: str


class ConnectorIdResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


class ConnectorCapabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    capability_kind: str
    capability_key: str


CONNECTOR_PERMISSION_IDENTITY = TableIdentity("mcp_group_connector_permissions")
CONNECTOR_PERMISSION_GROUP_ID = Field[GroupConnectorPermissionRecord, str](
    CONNECTOR_PERMISSION_IDENTITY, "group_id", TextCodec()
)
CONNECTOR_PERMISSION_CONNECTOR_ID = Field[GroupConnectorPermissionRecord, str](
    CONNECTOR_PERMISSION_IDENTITY, "connector_id", TextCodec()
)
_CONNECTOR_PERMISSION_FIELDS = cast(
    tuple[Field[GroupConnectorPermissionRecord, object], ...],
    (CONNECTOR_PERMISSION_GROUP_ID, CONNECTOR_PERMISSION_CONNECTOR_ID),
)
CONNECTOR_PERMISSION_TABLE = Table(
    CONNECTOR_PERMISSION_IDENTITY,
    RowCodec(GroupConnectorPermissionRecord, _CONNECTOR_PERMISSION_FIELDS),
    KeyCodec(GroupConnectorPermissionKey, _CONNECTOR_PERMISSION_FIELDS),
)
CONNECTOR_PERMISSION_GROUP_ID_PROJECTION = Fields(
    GroupIdResult,
    cast(
        tuple[Field[GroupConnectorPermissionRecord, object], ...], (CONNECTOR_PERMISSION_GROUP_ID,)
    ),
)
CONNECTOR_ID_PROJECTION = Fields(
    ConnectorIdResult,
    cast(
        tuple[Field[GroupConnectorPermissionRecord, object], ...],
        (CONNECTOR_PERMISSION_CONNECTOR_ID,),
    ),
)

CAPABILITY_PERMISSION_IDENTITY = TableIdentity("mcp_group_capability_permissions")
CAPABILITY_PERMISSION_GROUP_ID = Field[GroupCapabilityPermissionRecord, str](
    CAPABILITY_PERMISSION_IDENTITY, "group_id", TextCodec()
)
CAPABILITY_PERMISSION_CONNECTOR_ID = Field[GroupCapabilityPermissionRecord, str](
    CAPABILITY_PERMISSION_IDENTITY, "connector_id", TextCodec()
)
CAPABILITY_PERMISSION_KIND = Field[GroupCapabilityPermissionRecord, str](
    CAPABILITY_PERMISSION_IDENTITY, "capability_kind", TextCodec()
)
CAPABILITY_PERMISSION_KEY = Field[GroupCapabilityPermissionRecord, str](
    CAPABILITY_PERMISSION_IDENTITY, "capability_key", TextCodec()
)
_CAPABILITY_PERMISSION_FIELDS = cast(
    tuple[Field[GroupCapabilityPermissionRecord, object], ...],
    (
        CAPABILITY_PERMISSION_GROUP_ID,
        CAPABILITY_PERMISSION_CONNECTOR_ID,
        CAPABILITY_PERMISSION_KIND,
        CAPABILITY_PERMISSION_KEY,
    ),
)
CAPABILITY_PERMISSION_TABLE = Table(
    CAPABILITY_PERMISSION_IDENTITY,
    RowCodec(GroupCapabilityPermissionRecord, _CAPABILITY_PERMISSION_FIELDS),
    KeyCodec(GroupCapabilityPermissionKey, _CAPABILITY_PERMISSION_FIELDS),
)
CAPABILITY_PERMISSION_GROUP_ID_PROJECTION = Fields(
    GroupIdResult,
    cast(
        tuple[Field[GroupCapabilityPermissionRecord, object], ...],
        (CAPABILITY_PERMISSION_GROUP_ID,),
    ),
)
CONNECTOR_CAPABILITY_PROJECTION = Fields(
    ConnectorCapabilityResult,
    cast(
        tuple[Field[GroupCapabilityPermissionRecord, object], ...],
        (
            CAPABILITY_PERMISSION_CONNECTOR_ID,
            CAPABILITY_PERMISSION_KIND,
            CAPABILITY_PERMISSION_KEY,
        ),
    ),
)

GROUPS = GROUP_TABLE
CONNECTOR_PERMISSIONS = CONNECTOR_PERMISSION_TABLE
CAPABILITY_PERMISSIONS = CAPABILITY_PERMISSION_TABLE
TOOL_PERMISSION_TABLE = CAPABILITY_PERMISSION_TABLE
