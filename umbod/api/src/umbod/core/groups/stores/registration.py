from uuid import uuid4

from umbod.core.groups.models import GroupInstanceId, RegisterGroupMetadata
from umbod.core.persistence import (
    DatabaseSession,
    Equals,
    InsertCommand,
    Query,
    Unordered,
)

from .schema import (
    GROUP_ID,
    GROUP_ID_PROJECTION,
    GROUP_INSTANCE_RESERVATION_TABLE,
    GROUP_TABLE,
    GroupInstanceReservation,
    PermissionGroupRecord,
)

_INSTANCE_ALLOCATION_ATTEMPTS = 4


async def register_group_in_session(session: DatabaseSession, group_id: str) -> None:
    await _insert_group_if_missing(session, group_id, group_id, "")


async def register_group_metadata_in_session(
    session: DatabaseSession, request: RegisterGroupMetadata
) -> None:
    await _insert_group_if_missing(
        session, request.group_id, request.label, request.description
    )


async def _insert_group_if_missing(
    session: DatabaseSession, group_id: str, label: str, description: str
) -> None:
    existing = await session.find_one(
        GROUP_TABLE, Query(Equals(GROUP_ID, group_id), GROUP_ID_PROJECTION, Unordered())
    )
    if existing is not None:
        return
    await session.insert(
        GROUP_TABLE,
        InsertCommand(
            row=PermissionGroupRecord(
                group_id=group_id,
                label=label,
                description=description,
                revision=1,
                instance_id=await _reserve_instance_id(session),
            )
        ),
    )


async def _reserve_instance_id(session: DatabaseSession) -> GroupInstanceId:
    for _ in range(_INSTANCE_ALLOCATION_ATTEMPTS):
        reservation = GroupInstanceReservation(instance_id=uuid4().hex)
        if await session.insert(
            GROUP_INSTANCE_RESERVATION_TABLE, InsertCommand(row=reservation)
        ):
            return reservation.instance_id
    raise RuntimeError("Could not allocate a new group instance ID")
