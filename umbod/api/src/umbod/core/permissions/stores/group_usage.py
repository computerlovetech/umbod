from umbod.core.persistence import DatabaseSession, Query, Equals, Unordered
from .schema import (
    CONNECTOR_PERMISSION_TABLE,
    CONNECTOR_PERMISSION_GROUP_ID,
    CONNECTOR_PERMISSION_GROUP_ID_PROJECTION,
    CAPABILITY_PERMISSION_TABLE,
    CAPABILITY_PERMISSION_GROUP_ID,
    CAPABILITY_PERMISSION_GROUP_ID_PROJECTION,
)


class PermissionGroupUsage:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    async def is_in_use(self, group_id: str) -> bool:
        connector = await self._session.find_one(
            CONNECTOR_PERMISSION_TABLE,
            Query(
                Equals(CONNECTOR_PERMISSION_GROUP_ID, group_id),
                CONNECTOR_PERMISSION_GROUP_ID_PROJECTION,
                Unordered(),
            ),
        )
        capability = await self._session.find_one(
            CAPABILITY_PERMISSION_TABLE,
            Query(
                Equals(CAPABILITY_PERMISSION_GROUP_ID, group_id),
                CAPABILITY_PERMISSION_GROUP_ID_PROJECTION,
                Unordered(),
            ),
        )
        return connector is not None or capability is not None
