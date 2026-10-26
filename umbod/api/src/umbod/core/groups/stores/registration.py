from umbod.core.persistence import DatabaseSession, InsertCommand

from .schema import GROUP_TABLE, PermissionGroupRecord


async def register_group_in_session(session: DatabaseSession, group_id: str) -> None:
    await session.insert(
        GROUP_TABLE, InsertCommand(row=PermissionGroupRecord(group_id=group_id))
    )
