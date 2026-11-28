from typing import cast

from pydantic import ConfigDict

from umbod.proxies import Model
from umbod.core.groups.models import Group, GroupInstance, GroupInstanceId

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
    instance_id: GroupInstanceId

    def to_group(self) -> Group:
        return Group(
            group_id=self.group_id,
            label=self.label,
            description=self.description,
            revision=self.revision,
        )


class PermissionGroupKey(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str


class GroupIdResult(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str


GROUP_IDENTITY = TableIdentity("mcp_permission_groups")
GROUP_ID = Field[PermissionGroupRecord, str](GROUP_IDENTITY, "group_id", TextCodec())
GROUP_LABEL = Field[PermissionGroupRecord, str](GROUP_IDENTITY, "label", TextCodec())
GROUP_DESCRIPTION = Field[PermissionGroupRecord, str](GROUP_IDENTITY, "description", TextCodec())
GROUP_REVISION = Field[PermissionGroupRecord, int](GROUP_IDENTITY, "revision", IntegerCodec())
GROUP_INSTANCE_ID = Field[PermissionGroupRecord, str](GROUP_IDENTITY, "instance_id", TextCodec())
GROUP_TABLE = Table(
    GROUP_IDENTITY,
    RowCodec(
        PermissionGroupRecord,
        cast(
            tuple[Field[PermissionGroupRecord, object], ...],
            (GROUP_ID, GROUP_LABEL, GROUP_DESCRIPTION, GROUP_REVISION, GROUP_INSTANCE_ID),
        ),
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

GROUP_INSTANCE_PROJECTION = Fields(
    GroupInstance,
    cast(tuple[Field[PermissionGroupRecord, object], ...], (GROUP_ID, GROUP_INSTANCE_ID)),
)

class GroupInstanceReservation(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instance_id: GroupInstanceId


_RESERVATION_IDENTITY = TableIdentity("mcp_permission_group_instance_reservations")
_RESERVATION_INSTANCE_ID = Field[GroupInstanceReservation, str](
    _RESERVATION_IDENTITY, "instance_id", TextCodec()
)
_RESERVATION_FIELDS = cast(
    tuple[Field[GroupInstanceReservation, object], ...], (_RESERVATION_INSTANCE_ID,)
)
GROUP_INSTANCE_RESERVATION_TABLE = Table(
    _RESERVATION_IDENTITY,
    RowCodec(GroupInstanceReservation, _RESERVATION_FIELDS),
    KeyCodec(GroupInstanceReservation, _RESERVATION_FIELDS),
)

GROUPS = GROUP_TABLE
